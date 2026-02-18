import { PostHogSpanProcessor } from '@posthog/ai/otel';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { trace } from '@opentelemetry/api';
import { PostHog } from 'posthog-node';
import { generateText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { BaseProvider, Message, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class VercelAIOtelOpenAIProvider extends BaseProvider {
  private openaiClient: any;
  private static otelSdkStarted = false;
  private static otelSdk: NodeSDK | null = null;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.openaiClient = createOpenAI({
      apiKey: process.env.OPENAI_API_KEY!
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
    // Vercel AI SDK tool declarations are passed directly to generateText
    return [];
  }

  getName(): string {
    return 'Vercel AI SDK OTEL (OpenAI)';
  }

  private async ensureOtelSdk(): Promise<void> {
    if (VercelAIOtelOpenAIProvider.otelSdkStarted) {
      return;
    }

    VercelAIOtelOpenAIProvider.otelSdk = new NodeSDK({
      spanProcessors: [
        new PostHogSpanProcessor(this.posthogClient),
      ],
    });
    VercelAIOtelOpenAIProvider.otelSdk.start();
    VercelAIOtelOpenAIProvider.otelSdkStarted = true;
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    await this.ensureOtelSdk();

    const userMessage: Message = {
      role: 'user',
      content: base64Image
        ? [
            { type: 'text', text: userInput },
            {
              type: 'image',
              image: `data:image/png;base64,${base64Image}`
            }
          ]
        : userInput
    };
    this.messages.push(userMessage);

    const modelName = base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL;
    const model = this.openaiClient(modelName);
    const posthogDistinctId = process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID;

    const telemetryMetadata: Record<string, string> = {
      posthog_distinct_id: posthogDistinctId,
      provider: 'vercel-ai-sdk-otel-openai',
    };

    if (this.aiSessionId) {
      telemetryMetadata.ai_session_id = this.aiSessionId;
    }

    const requestParams = {
      model,
      messages: this.messages as any,
      maxOutputTokens: DEFAULT_MAX_TOKENS,
      experimental_telemetry: {
        isEnabled: true,
        functionId: 'vercel-ai-otel-openai-chat',
        metadata: telemetryMetadata,
      },
      tools: {
        get_weather: {
          description: 'Get the current weather for a specific location',
          inputSchema: z.object({
            latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
            longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
            location_name: z.string().describe('A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')')
          }),
          execute: async ({ latitude, longitude, location_name }: { latitude: number; longitude: number; location_name: string }) => {
            return this.getWeather(latitude, longitude, location_name);
          }
        },
        tell_joke: {
          description: 'Tell a joke with a question-style setup and an answer punchline',
          inputSchema: z.object({
            setup: z.string().describe('The setup of the joke, usually in question form'),
            punchline: z.string().describe('The punchline or answer to the joke')
          }),
          execute: async ({ setup, punchline }: { setup: string; punchline: string }) => {
            return this.tellJoke(setup, punchline);
          }
        }
      }
    };

    try {
      const tracer = trace.getTracer('vercel-ai-otel-openai-provider');
      return await tracer.startActiveSpan('vercel-ai-otel-openai-two-part-chat', async (span) => {
        try {
          const displayParts: string[] = [];
          const partOneParams = {
            model,
            messages: [
              {
                role: 'system',
                content: 'Output exactly this text and nothing else: PART 1/2: Let me check that.'
              }
            ] as any,
            maxOutputTokens: 256,
            experimental_telemetry: {
              isEnabled: true,
              functionId: 'vercel-ai-otel-openai-chat-part1',
              metadata: {
                ...telemetryMetadata,
                forced_response_part: '1'
              },
            },
          };

          const { text: partOneText } = await generateText(partOneParams as any);
          this.debugApiCall('Vercel AI SDK OTEL (OpenAI) - Part 1', { ...partOneParams, model: modelName }, { text: partOneText });

          const partOneDisplayText = partOneText?.trim() || 'PART 1/2: Let me check that.';
          displayParts.push(partOneDisplayText);
          this.messages.push({
            role: 'assistant',
            content: partOneDisplayText
          });

          const finalRequestParams = {
            ...requestParams,
            experimental_telemetry: {
              ...requestParams.experimental_telemetry,
              functionId: 'vercel-ai-otel-openai-chat-part2',
              metadata: {
                ...telemetryMetadata,
                forced_response_part: '2'
              },
            }
          };

          const { text, toolResults } = await generateText(finalRequestParams as any);
          this.debugApiCall('Vercel AI SDK OTEL (OpenAI)', { ...finalRequestParams, model: modelName }, { text, toolResults });

          if (text) {
            displayParts.push(text);
            this.messages.push({
              role: 'assistant',
              content: text
            });
          }

          if (toolResults && toolResults.length > 0) {
            for (const result of toolResults) {
              if (result.toolName === 'get_weather' && 'output' in result) {
                displayParts.push(this.formatToolResult('get_weather', result.output as string));
              } else if (result.toolName === 'tell_joke' && 'output' in result) {
                displayParts.push(this.formatToolResult('tell_joke', result.output as string));
              }
            }
          }

          return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
        } finally {
          span.end();
        }
      });
    } catch (error: any) {
      console.error('Error in Vercel AI OTEL OpenAI chat:', error);
      throw new Error(`Vercel AI OTEL OpenAI Provider error: ${error.message}`);
    }
  }
}
