/**
 * Vercel AI SDK provider with raw OpenTelemetry OTLP export.
 *
 * Unlike the other Vercel AI OTel providers that use PostHogSpanProcessor,
 * this provider sends OTel spans directly to PostHog's OTLP ingestion
 * endpoint (/i/v0/ai/otel) using the standard OTLP HTTP exporter.
 * This mirrors the approach used by the Python LangChain and Pydantic AI
 * OTel providers.
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { PostHog } from 'posthog-node';
import type { ModelMessage } from 'ai';
import { generateText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { BaseProvider, Tool } from './base.js';
import {
  OPENAI_CHAT_MODEL,
  OPENAI_VISION_MODEL,
  DEFAULT_MAX_TOKENS,
  DEFAULT_POSTHOG_DISTINCT_ID,
  SYSTEM_PROMPT_ASSISTANT,
} from './constants.js';

export class VercelAIOtelProvider extends BaseProvider {
  private openai: ReturnType<typeof createOpenAI>;
  private vercelMessages: ModelMessage[] = [];
  private static otelConfigured = false;
  private static otelSdk: NodeSDK | null = null;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.setupOtel();
    this.openai = createOpenAI({
      apiKey: process.env.OPENAI_API_KEY!,
    });
    this.vercelMessages = [
      { role: 'system', content: SYSTEM_PROMPT_ASSISTANT },
    ];
  }

  private setupOtel(): void {
    if (VercelAIOtelProvider.otelConfigured) {
      return;
    }

    const posthogApiKey = process.env.POSTHOG_API_KEY;
    const posthogHost = process.env.POSTHOG_HOST || 'http://localhost:8010';

    if (!posthogApiKey) {
      throw new Error('POSTHOG_API_KEY must be set');
    }

    const resourceAttributes: Record<string, string> = {
      'service.name': 'llm-analytics-app-vercel-ai-otel',
      'user.id': process.env.POSTHOG_DISTINCT_ID || 'unknown',
    };
    if (this.debugMode) {
      resourceAttributes['posthog.ai.debug'] = 'true';
    }

    const exporter = new OTLPTraceExporter({
      url: `${posthogHost}/i/v0/ai/otel`,
      headers: {
        Authorization: `Bearer ${posthogApiKey}`,
      },
    });

    VercelAIOtelProvider.otelSdk = new NodeSDK({
      resource: resourceFromAttributes(resourceAttributes),
      traceExporter: exporter,
    });
    VercelAIOtelProvider.otelSdk.start();

    VercelAIOtelProvider.otelConfigured = true;
  }

  protected getToolDefinitions(): Tool[] {
    return [];
  }

  getName(): string {
    return 'Vercel AI SDK (Raw OTel)';
  }

  resetConversation(): void {
    this.vercelMessages = [
      { role: 'system', content: SYSTEM_PROMPT_ASSISTANT },
    ];
    this.messages = [];
  }

  private buildTools() {
    return {
      get_weather: {
        description: 'Get the current weather for a specific location',
        inputSchema: z.object({
          latitude: z.number().describe('The latitude of the location'),
          longitude: z.number().describe('The longitude of the location'),
          location_name: z.string().describe('A human-readable name for the location'),
        }),
        execute: async ({
          latitude,
          longitude,
          location_name,
        }: {
          latitude: number;
          longitude: number;
          location_name: string;
        }) => {
          return this.getWeather(latitude, longitude, location_name);
        },
      },
      tell_joke: {
        description: 'Tell a joke with a question-style setup and an answer punchline',
        inputSchema: z.object({
          setup: z.string().describe('The setup of the joke, usually in question form'),
          punchline: z.string().describe('The punchline or answer to the joke'),
        }),
        execute: async ({ setup, punchline }: { setup: string; punchline: string }) => {
          return this.tellJoke(setup, punchline);
        },
      },
    };
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    const userMessage: ModelMessage = base64Image
      ? {
          role: 'user',
          content: [
            { type: 'text', text: userInput },
            { type: 'image', image: `data:image/png;base64,${base64Image}` },
          ],
        }
      : { role: 'user', content: [{ type: 'text', text: userInput }] };
    this.vercelMessages.push(userMessage);

    const modelName = base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL;
    const posthogDistinctId = process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID;

    const telemetryMetadata: Record<string, string> = {
      posthog_distinct_id: posthogDistinctId,
      provider: 'vercel-ai-sdk-raw-otel',
    };

    if (this.aiSessionId) {
      telemetryMetadata.ai_session_id = this.aiSessionId;
    }

    try {
      const { text, toolResults } = await generateText({
        model: this.openai(modelName),
        messages: this.vercelMessages,
        maxOutputTokens: DEFAULT_MAX_TOKENS,
        experimental_telemetry: {
          isEnabled: true,
          functionId: 'vercel-ai-raw-otel-chat',
          metadata: telemetryMetadata,
        },
        tools: this.buildTools(),
      });

      this.debugApiCall(
        'Vercel AI SDK (Raw OTel)',
        { model: modelName, messages: this.vercelMessages },
        { text, toolResults },
      );

      const displayParts: string[] = [];

      if (text) {
        displayParts.push(text);
        this.vercelMessages.push({ role: 'assistant', content: [{ type: 'text', text }] });
      }

      if (toolResults && toolResults.length > 0) {
        for (const result of toolResults) {
          if ('output' in result && typeof result.output === 'string') {
            displayParts.push(this.formatToolResult(result.toolName, result.output));
          }
        }
      }

      return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      console.error('Error in Vercel AI Raw OTel chat:', error);
      throw new Error(`Vercel AI Raw OTel Provider error: ${message}`);
    }
  }
}
