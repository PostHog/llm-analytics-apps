// @ts-nocheck
import { PostHogSpanProcessor } from '@posthog/ai/otel';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { generateText } from 'ai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { BaseProvider } from './base.js';
import { GEMINI_IMAGE_MODEL, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';
export class VercelAIOtelGeminiImageProvider extends BaseProvider {
    googleClient;
    static otelSdkStarted = false;
    static otelSdk = null;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.googleClient = createGoogleGenerativeAI({
            apiKey: process.env.GEMINI_API_KEY
        });
    }
    getToolDefinitions() {
        return [];
    }
    getName() {
        return 'Vercel AI SDK OTEL (Gemini + Image Gen)';
    }
    async ensureOtelSdk() {
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
    getTelemetryMetadata() {
        const metadata = {
            posthog_distinct_id: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            provider: 'vercel-ai-sdk-otel-gemini-image',
        };
        if (this.aiSessionId) {
            metadata.ai_session_id = this.aiSessionId;
        }
        return metadata;
    }
    async generateImage(prompt, model = GEMINI_IMAGE_MODEL) {
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
    async chat() {
        throw new Error('This provider is for image generation only. Use generateImage() instead.');
    }
}
//# sourceMappingURL=vercel-ai-otel-gemini-image.js.map