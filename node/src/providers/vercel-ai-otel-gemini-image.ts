import { PostHogSpanProcessor } from '@posthog/ai/otel';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { PostHog } from 'posthog-node';
import { generateText } from 'ai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { BaseProvider, Tool } from './base.js';
import { GEMINI_IMAGE_MODEL, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';

export class VercelAIOtelGeminiImageProvider extends BaseProvider {
  private googleClient: any;
  private static otelSdkStarted = false;
  private static otelSdk: NodeSDK | null = null;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.googleClient = createGoogleGenerativeAI({
      apiKey: process.env.GEMINI_API_KEY!
    });
  }

  protected getToolDefinitions(): Tool[] {
    return [];
  }

  getName(): string {
    return 'Vercel AI SDK OTEL (Gemini + Image Gen)';
  }

  private async ensureOtelSdk(): Promise<void> {
    if (VercelAIOtelGeminiImageProvider.otelSdkStarted) {
      return;
    }

    VercelAIOtelGeminiImageProvider.otelSdk = new NodeSDK({
      spanProcessors: [
        new PostHogSpanProcessor(this.posthogClient),
      ],
    });
    VercelAIOtelGeminiImageProvider.otelSdk.start();
    VercelAIOtelGeminiImageProvider.otelSdkStarted = true;
  }

  private getTelemetryMetadata(): Record<string, string> {
    const metadata: Record<string, string> = {
      posthog_distinct_id: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      provider: 'vercel-ai-sdk-otel-gemini-image',
    };

    if (this.aiSessionId) {
      metadata.ai_session_id = this.aiSessionId;
    }

    return metadata;
  }

  async generateImage(prompt: string, model: string = GEMINI_IMAGE_MODEL): Promise<string> {
    await this.ensureOtelSdk();

    const result = await generateText({
      model: this.googleClient(model),
      prompt,
      experimental_telemetry: {
        isEnabled: true,
        functionId: 'vercel-ai-otel-gemini-image-generate',
        metadata: this.getTelemetryMetadata(),
      },
    });

    this.debugApiCall('Vercel AI SDK OTEL (Gemini + Image Gen)', { model, prompt }, result);

    if (result.files && result.files.length > 0) {
      for (const file of result.files) {
        if (file.mediaType?.startsWith('image/')) {
          const b64 = Buffer.from(file.uint8Array).toString('base64');
          return `data:${file.mediaType};base64,${b64.substring(0, 100)}... (base64 image data, ${b64.length} chars total)`;
        }
      }
    }

    return '';
  }

  async chat(): Promise<string> {
    throw new Error('This provider is for image generation only. Use generateImage() instead.');
  }
}
