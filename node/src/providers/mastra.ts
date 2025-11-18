import { PostHog } from 'posthog-node';
import { Mastra } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import { randomUUID } from 'crypto';
import { BaseProvider, Message, Tool } from './base.js';
import { DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

/**
 * Mastra Provider with Manual PostHog Instrumentation
 *
 * This provider demonstrates how to manually capture LLM analytics events
 * when using an AI framework that isn't natively supported by PostHog SDK.
 *
 * Manual capture involves:
 * 1. Generating trace and span IDs
 * 2. Tracking timing (latency)
 * 3. Estimating or extracting token counts
 * 4. Calling posthog.capture() with the correct event type and properties
 */
export class MastraProvider extends BaseProvider {
  private mastra: Mastra;
  private agent: Agent;
  private traceId: string;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);

    // Generate a trace ID for this conversation
    this.traceId = this.generateTraceId();

    // Create Mastra tools
    const weatherTool = createTool({
      id: 'get-weather',
      description: 'Get the current weather for a specific location',
      inputSchema: z.object({
        latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
        longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
        location_name: z.string().describe("A human-readable name for the location (e.g., 'San Francisco, CA')"),
      }),
      outputSchema: z.object({
        result: z.string(),
      }),
      execute: async ({ context }) => {
        const result = await this.getWeather(
          context.latitude,
          context.longitude,
          context.location_name
        );
        return { result };
      },
    });

    const jokeTool = createTool({
      id: 'tell-joke',
      description: 'Tell a joke with a question-style setup and an answer punchline',
      inputSchema: z.object({
        setup: z.string().describe('The setup of the joke, usually in question form'),
        punchline: z.string().describe('The punchline or answer to the joke'),
      }),
      outputSchema: z.object({
        result: z.string(),
      }),
      execute: async ({ context }) => {
        const result = await this.tellJoke(context.setup, context.punchline);
        return { result };
      },
    });

    // Create Mastra agent with tools
    this.agent = new Agent({
      name: 'Assistant',
      instructions: SYSTEM_PROMPT_FRIENDLY,
      // Mastra uses provider/model format
      model: { id: 'openai/gpt-4o-mini' },
      tools: { weatherTool, jokeTool },
    });

    // Initialize Mastra with the agent
    this.mastra = new Mastra({
      agents: { assistant: this.agent },
    });

    this.messages = this.getInitialMessages();
  }

  protected getInitialMessages(): Message[] {
    return [
      {
        role: 'system',
        content: SYSTEM_PROMPT_FRIENDLY
      }
    ];
  }

  protected getToolDefinitions(): Tool[] {
    // Mastra handles tools internally
    return [];
  }

  getName(): string {
    return 'Mastra (OpenAI) - Manual Instrumentation';
  }

  /**
   * Generate a valid trace ID (UUID format)
   */
  private generateTraceId(): string {
    return randomUUID();
  }

  /**
   * Generate a unique span ID for individual operations
   */
  private generateSpanId(): string {
    return randomUUID();
  }

  /**
   * Manually capture a PostHog span event (for tool calls, etc.)
   */
  private captureSpan(
    spanName: string,
    inputState: any,
    outputState: any,
    latency: number,
    spanId: string,
    parentId: string
  ): void {
    this.posthogClient.capture({
      distinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      event: '$ai_span',
      properties: {
        $ai_trace_id: this.traceId,
        $ai_span_id: spanId,
        $ai_span_name: spanName,
        $ai_parent_id: parentId,
        $ai_input_state: inputState,
        $ai_output_state: outputState,
        $ai_latency: latency,
        $ai_is_error: false,
        ...this.getPostHogProperties(),
      },
    });

    this.debugLog('PostHog Span Capture', {
      event: '$ai_span',
      span_name: spanName,
      span_id: spanId,
      parent_id: parentId,
      latency,
    });
  }

  /**
   * Manually capture a PostHog generation event
   */
  private captureGeneration(
    input: any[],
    output: any[],
    latency: number,
    inputTokens: number,
    outputTokens: number,
    spanId: string,
    parentId?: string
  ): void {
    const properties: Record<string, any> = {
      // Core required properties
      $ai_trace_id: this.traceId,
      $ai_model: 'gpt-4o-mini',
      $ai_provider: 'mastra',
      $ai_input: input,
      $ai_output_choices: output,
      $ai_input_tokens: inputTokens,
      $ai_output_tokens: outputTokens,

      // Optional but recommended properties
      $ai_span_id: spanId,
      $ai_span_name: 'mastra_chat',
      $ai_latency: latency,
      $ai_is_error: false,
      $ai_stream: false,

      // Add session ID if available
      ...this.getPostHogProperties(),
    };

    if (parentId) {
      properties.$ai_parent_id = parentId;
    }

    // Manually capture the event
    this.posthogClient.capture({
      distinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      event: '$ai_generation',
      properties,
    });

    this.debugLog('PostHog Manual Capture', {
      event: '$ai_generation',
      trace_id: this.traceId,
      span_id: spanId,
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      latency,
    });
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    // Add user message to history
    const userMessage: Message = {
      role: 'user',
      content: userInput
    };
    this.messages.push(userMessage);

    // Generate a span ID for this generation
    const spanId = this.generateSpanId();
    const startTime = Date.now();

    try {
      this.debugLog('Mastra Request', {
        user_input: userInput,
        model: 'gpt-4o-mini',
        message_count: this.messages.length,
      });

      // Use Mastra agent to generate response with full conversation history
      // Mastra's generate() accepts message arrays in CoreMessage format
      const response = await this.agent.generate(this.messages as any);

      // Calculate latency in seconds
      const latency = (Date.now() - startTime) / 1000;

      // Extract response data from Mastra
      const assistantContent = response.text || '';

      // Extract token counts from Mastra response
      // Mastra uses: inputTokens, outputTokens, totalTokens, reasoningTokens, cachedInputTokens
      const inputTokens = (response.usage as any)?.inputTokens || 0;
      const outputTokens = (response.usage as any)?.outputTokens || 0;
      const totalTokens = (response.usage as any)?.totalTokens || 0;
      const reasoningTokens = (response.usage as any)?.reasoningTokens || 0;
      const cachedInputTokens = (response.usage as any)?.cachedInputTokens || 0;

      this.debugLog('Mastra Response', {
        text: assistantContent.substring(0, 100) + (assistantContent.length > 100 ? '...' : ''),
        latency,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: totalTokens,
        reasoning_tokens: reasoningTokens,
        cached_input_tokens: cachedInputTokens,
        finish_reason: response.finishReason,
        tool_calls: response.toolCalls?.length || 0,
        tool_results: response.toolResults?.length || 0,
      });

      // Manually capture tool calls as spans
      if (response.toolCalls && response.toolCalls.length > 0) {
        for (let i = 0; i < response.toolCalls.length; i++) {
          const toolCall = response.toolCalls[i];
          const toolResult = response.toolResults?.[i];

          // Generate a unique span ID for this tool call
          const toolSpanId = this.generateSpanId();

          // Capture the tool execution as a span
          this.captureSpan(
            toolCall.toolName,
            toolCall.args,
            toolResult?.result || toolResult,
            0, // Mastra doesn't provide individual tool latency
            toolSpanId,
            spanId // Parent is the generation span
          );
        }
      }

      // Manually capture PostHog generation event
      this.captureGeneration(
        this.messages.map(m => ({
          role: m.role,
          content: Array.isArray(m.content) ? m.content : [{ type: 'text', text: m.content }]
        })),
        [{
          role: 'assistant',
          content: [{ type: 'text', text: assistantContent }]
        }],
        latency,
        inputTokens,
        outputTokens,
        spanId
      );

      // Add assistant response to message history
      const assistantMessage: Message = {
        role: 'assistant',
        content: assistantContent
      };
      this.messages.push(assistantMessage);

      return assistantContent || 'No response received';

    } catch (error: any) {
      const latency = (Date.now() - startTime) / 1000;

      // Capture error event
      this.posthogClient.capture({
        distinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        event: '$ai_generation',
        properties: {
          $ai_trace_id: this.traceId,
          $ai_span_id: spanId,
          $ai_span_name: 'mastra_chat',
          $ai_model: 'gpt-4o-mini',
          $ai_provider: 'mastra',
          $ai_latency: latency,
          $ai_is_error: true,
          $ai_error: error.message,
          ...this.getPostHogProperties(),
        },
      });

      console.error('Error in Mastra chat:', error);
      throw new Error(`Mastra Provider error: ${error.message}`);
    }
  }
}
