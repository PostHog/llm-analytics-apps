import { withTracing } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { streamText, tool } from 'ai';
import { createAnthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { StreamingProvider, Message, Tool } from './base.js';
import { ANTHROPIC_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class VercelAIAnthropicStreamingProvider extends StreamingProvider {
  private anthropicClient: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.anthropicClient = createAnthropic({
      apiKey: process.env.ANTHROPIC_API_KEY!
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
    // Vercel AI SDK doesn't use this, but we need to implement it
    return [];
  }

  getName(): string {
    return 'Vercel AI SDK Streaming (Anthropic)';
  }

  async *chatStream(
    userInput: string,
    base64Image?: string
  ): AsyncGenerator<string, void, unknown> {
    let userContent: any;

    if (base64Image) {
      // For image input, create content array with text and image
      userContent = [
        { type: 'text', text: userInput },
        {
          type: 'image',
          image: `data:image/png;base64,${base64Image}`
        }
      ];
    } else {
      userContent = userInput;
    }

    const userMessage: Message = {
      role: 'user',
      content: userContent
    };
    this.messages.push(userMessage);

    const model = withTracing(this.anthropicClient(ANTHROPIC_MODEL), this.posthogClient, {
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      posthogPrivacyMode: false,
      posthogProperties: {
        $ai_span_name: "vercel_ai_stream_text_anthropic",
        ...this.getPostHogProperties(),
      },
    });

    try {
      const requestParams = {
        model: model,
        messages: this.messages as any,
        maxOutputTokens: DEFAULT_MAX_TOKENS,
        tools: {
          get_weather: tool({
            description: 'Get the current weather for a specific location',
            inputSchema: z.object({
              latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
              longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
              location_name: z.string().describe('A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')')
            }),
            execute: async ({ latitude, longitude, location_name }: { latitude: number; longitude: number; location_name: string }) => {
              return this.getWeather(latitude, longitude, location_name);
            }
          }),
          tell_joke: tool({
            description: 'Tell a joke with a question-style setup and an answer punchline',
            inputSchema: z.object({
              setup: z.string().describe('The setup of the joke, usually in question form'),
              punchline: z.string().describe('The punchline or answer to the joke')
            }),
            execute: async ({ setup, punchline }: { setup: string; punchline: string }) => {
              return this.tellJoke(setup, punchline);
            }
          })
        }
      };

      if (this.debugMode) {
        this.debugLog("Vercel AI SDK Streaming (Anthropic) API Request", requestParams);
      }

      const result = await streamText(requestParams);

      let accumulatedContent = '';
      const toolCalls: any[] = [];
      let currentToolCall: any = null;

      for await (const part of result.fullStream) {
        // Handle text delta events
        if (part.type === 'text-delta') {
          const delta = (part as any).text || '';
          accumulatedContent += delta;
          yield delta;
        }

        // Handle tool call start
        if (part.type === 'tool-call') {
          currentToolCall = {
            toolName: (part as any).toolName,
            args: (part as any).input || {}
          };
          toolCalls.push(currentToolCall);
        }

        // Handle tool result
        if (part.type === 'tool-result') {
          const toolResult = part as any;
          if (toolResult.toolName === 'get_weather') {
            // The tool was already executed via the execute function
            // Format and yield the result
            const weatherResult = toolResult.output as string;
            const toolResultText = this.formatToolResult('get_weather', weatherResult);
            yield '\n\n' + toolResultText;
          } else if (toolResult.toolName === 'tell_joke') {
            // The tool was already executed via the execute function
            // Format and yield the result
            const jokeResult = toolResult.output as string;
            const toolResultText = this.formatToolResult('tell_joke', jokeResult);
            yield '\n\n' + toolResultText;
          }
        }

        // Handle finish event for usage tracking
        if (part.type === 'finish') {
          // Usage information is available in part.usage if needed
          // but we're already tracking this via withTracing
        }
      }

      // Save assistant message with accumulated content
      if (accumulatedContent) {
        const assistantMessage: Message = {
          role: 'assistant',
          content: accumulatedContent
        };
        this.messages.push(assistantMessage);
      } else if (toolCalls.length > 0) {
        // If there was a tool call but no text content, save the tool result as assistant message
        let toolResultsText = '';
        for (const toolCall of toolCalls) {
          if (toolCall.toolName === 'get_weather') {
            const latitude = toolCall.args.latitude || 0.0;
            const longitude = toolCall.args.longitude || 0.0;
            const locationName = toolCall.args.location_name;
            const weatherResult = await this.getWeather(latitude, longitude, locationName);
            toolResultsText += this.formatToolResult('get_weather', weatherResult);
          } else if (toolCall.toolName === 'tell_joke') {
            const setup = toolCall.args.setup || '';
            const punchline = toolCall.args.punchline || '';
            const jokeResult = this.tellJoke(setup, punchline);
            toolResultsText += this.formatToolResult('tell_joke', jokeResult);
          }
        }

        if (toolResultsText) {
          const assistantMessage: Message = {
            role: 'assistant',
            content: toolResultsText
          };
          this.messages.push(assistantMessage);
        }
      }

      // Debug: Log the completed stream response
      if (this.debugMode) {
        this.debugLog("Vercel AI SDK Streaming (Anthropic) API Response (completed)", {
          accumulatedContent: accumulatedContent,
          toolCalls: toolCalls
        });
      }
    } catch (error: any) {
      console.error('Error in Vercel AI Anthropic streaming chat:', error);
      throw new Error(`Vercel AI Anthropic Streaming Provider error: ${error.message}`);
    }
  }

  // Non-streaming chat for compatibility
  async chat(userInput: string, base64Image?: string): Promise<string> {
    const chunks: string[] = [];
    for await (const chunk of this.chatStream(userInput, base64Image)) {
      chunks.push(chunk);
    }
    return chunks.join('');
  }
}
