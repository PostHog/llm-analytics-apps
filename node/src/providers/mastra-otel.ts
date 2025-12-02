import { PostHog } from 'posthog-node';
import { Mastra, createTool } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { OtelExporter } from '@mastra/otel-exporter';
import { z } from 'zod';
import { trace } from '@opentelemetry/api';
import { BaseProvider, Message, Tool } from './base.js';
import { SYSTEM_PROMPT_FRIENDLY } from './constants.js';

/**
 * Mastra Provider with OTEL Instrumentation
 *
 * This provider demonstrates automatic instrumentation using Mastra's
 * OpenTelemetry exporter. Instead of manually capturing events, Mastra
 * automatically generates OTEL spans and sends them to PostHog's OTEL endpoint.
 *
 * Benefits:
 * - Automatic trace hierarchy (parent-child relationships)
 * - Automatic token counting
 * - Automatic tool call tracking
 * - No manual event capture code needed
 */
export class MastraOtelProvider extends BaseProvider {
  private mastra: Mastra;
  private agent: Agent;

  constructor(
    posthogClient: PostHog,
    aiSessionId: string | null = null,
    posthogHost: string = 'http://localhost:8000',
    projectId: string = '1',
    apiKey: string = 'phc_test'
  ) {
    super(posthogClient, aiSessionId);

    // Disable Mastra's old telemetry warning (we're using OTEL exporter instead)
    (globalThis as any).___MASTRA_TELEMETRY___ = true;

    // Configure OTEL endpoint
    const tracesEndpoint = `${posthogHost}/api/projects/${projectId}/ai/otel/v1/traces`;

    // Create Mastra tools
    const weatherTool = createTool({
      id: 'get-weather',
      description: 'Get the current weather for a specific location',
      inputSchema: z.object({
        location: z.string().describe('City name and country (e.g., "San Francisco, CA")'),
      }),
      outputSchema: z.object({
        weather: z.string(),
      }),
      execute: async ({ context }) => {
        // For simplicity, use fixed coordinates
        const result = await this.getWeather(
          37.7749,  // San Francisco latitude
          -122.4194, // San Francisco longitude
          context.location
        );
        return { weather: result };
      },
    });

    const jokeTool = createTool({
      id: 'tell-joke',
      description: 'Tell a joke about a given topic',
      inputSchema: z.object({
        topic: z.string().describe('The topic of the joke'),
      }),
      outputSchema: z.object({
        joke: z.string(),
      }),
      execute: async ({ context }) => {
        const result = await this.tellJoke(
          `Why did the ${context.topic} cross the road?`,
          `To get to the other side!`
        );
        return { joke: result };
      },
    });

    // Create Mastra agent with tools
    this.agent = new Agent({
      name: 'assistant',
      instructions: SYSTEM_PROMPT_FRIENDLY,
      model: { id: 'openai/gpt-4o-mini' },
      tools: { weatherTool, jokeTool },
    });

    // Initialize Mastra with OTEL exporter
    this.mastra = new Mastra({
      observability: {
        configs: {
          default: {
            serviceName: 'mastra-otel-provider',
            exporters: [
              new OtelExporter({
                provider: {
                  custom: {
                    endpoint: tracesEndpoint,
                    protocol: 'http/protobuf',
                    headers: {
                      'Authorization': `Bearer ${apiKey}`,
                    },
                  },
                },
                timeout: 60000,
                logLevel: 'info',
                resourceAttributes: {
                  'service.name': 'mastra-otel-provider',
                  'user.id': process.env.POSTHOG_DISTINCT_ID || 'llm-analytics-cli-user',
                },
              }),
            ],
          },
        },
      },
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
    return 'Mastra (OpenAI) - OTEL Instrumentation';
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    // Add user message to history
    const userMessage: Message = {
      role: 'user',
      content: userInput
    };
    this.messages.push(userMessage);

    try {
      this.debugLog('Mastra OTEL Request', {
        user_input: userInput,
        model: 'gpt-4o-mini',
        message_count: this.messages.length,
      });

      // Use Mastra agent to generate response
      // OTEL instrumentation happens automatically
      const response = await this.agent.generate(this.messages as any, {
        maxSteps: 5,
      });

      // Extract response data
      const assistantContent = response.text || '';

      this.debugLog('Mastra OTEL Response', {
        text: assistantContent.substring(0, 100) + (assistantContent.length > 100 ? '...' : ''),
        input_tokens: (response.usage as any)?.inputTokens || 0,
        output_tokens: (response.usage as any)?.outputTokens || 0,
        finish_reason: response.finishReason,
        tool_calls: response.toolCalls?.length || 0,
      });

      // Add assistant response to message history
      const assistantMessage: Message = {
        role: 'assistant',
        content: assistantContent
      };
      this.messages.push(assistantMessage);

      return assistantContent || 'No response received';

    } catch (error: any) {
      console.error('Error in Mastra OTEL chat:', error);
      throw new Error(`Mastra OTEL Provider error: ${error.message}`);
    }
  }

  /**
   * Flush OTEL spans before shutting down.
   * Call this when the CLI session ends to ensure all spans are sent.
   */
  async flush(): Promise<void> {
    try {
      const provider = trace.getTracerProvider();
      if (provider && 'forceFlush' in provider && typeof provider.forceFlush === 'function') {
        await provider.forceFlush();
        this.debugLog('OTEL Flush', { status: 'success' });
      } else {
        // Fallback: wait for auto-flush
        await new Promise(resolve => setTimeout(resolve, 5000));
        this.debugLog('OTEL Flush', { status: 'fallback_wait' });
      }
    } catch (error: any) {
      console.error('Error flushing OTEL spans:', error);
      // Wait a bit anyway
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
  }
}
