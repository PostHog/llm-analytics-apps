// @ts-nocheck
import { PostHogSpanProcessor } from '@posthog/ai/otel';
import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { generateText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { BaseProvider } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';
export class VercelAIOtelOpenAIImageProvider extends BaseProvider {
    openaiClient;
    imageClient;
    static otelSdkStarted = false;
    static otelSdk = null;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.openaiClient = createOpenAI({
            apiKey: process.env.OPENAI_API_KEY
        });
        this.imageClient = new PostHogOpenAI({
            apiKey: process.env.OPENAI_API_KEY,
            posthog: posthogClient
        });
        this.messages = this.getInitialMessages();
    }
    getInitialMessages() {
        return [
            {
                role: 'system',
                content: SYSTEM_PROMPT_FRIENDLY
            }
        ];
    }
    getToolDefinitions() {
        // Vercel AI SDK tool declarations are passed directly to generateText
        return [];
    }
    getName() {
        return 'Vercel AI SDK OTEL (OpenAI + Image Gen)';
    }
    async ensureOtelSdk() {
        if (VercelAIOtelOpenAIImageProvider.otelSdkStarted) {
            return;
        }
        VercelAIOtelOpenAIImageProvider.otelSdk = new NodeSDK({
            spanProcessors: [
                new PostHogSpanProcessor(this.posthogClient),
            ],
        });
        VercelAIOtelOpenAIImageProvider.otelSdk.start();
        VercelAIOtelOpenAIImageProvider.otelSdkStarted = true;
    }
    getTelemetryMetadata() {
        const metadata = {
            posthog_distinct_id: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            provider: 'vercel-ai-sdk-otel-openai-image',
        };
        if (this.aiSessionId) {
            metadata.ai_session_id = this.aiSessionId;
        }
        return metadata;
    }
    async generateImage(prompt, model = OPENAI_CHAT_MODEL) {
        try {
            const requestParams = {
                model,
                input: prompt,
                tools: [{ type: 'image_generation' }],
                posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
                posthogProperties: this.getPostHogProperties()
            };
            const response = await this.imageClient.responses.create(requestParams);
            this.debugApiCall('Vercel AI SDK OTEL (OpenAI + Image Gen)', requestParams, response);
            const imageData = response.output
                ?.filter((output) => output.type === 'image_generation_call')
                .map((output) => output.result);
            if (imageData && imageData.length > 0) {
                const imageBase64 = imageData[0];
                return `data:image/png;base64,${imageBase64.substring(0, 100)}... (base64 image data, ${imageBase64.length} chars total)`;
            }
            return '';
        }
        catch (error) {
            console.error('Error in Vercel AI OTEL OpenAI image generation:', error);
            throw new Error(`Vercel AI OTEL OpenAI Image Generation error: ${error.message}`);
        }
    }
    async chat(userInput, base64Image) {
        await this.ensureOtelSdk();
        const userMessage = {
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
        const requestParams = {
            model,
            messages: this.messages,
            maxOutputTokens: DEFAULT_MAX_TOKENS,
            experimental_telemetry: {
                isEnabled: true,
                functionId: 'vercel-ai-otel-openai-image-chat',
                metadata: this.getTelemetryMetadata(),
            },
            tools: {
                get_weather: {
                    description: 'Get the current weather for a specific location',
                    inputSchema: z.object({
                        latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
                        longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
                        location_name: z.string().describe('A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')')
                    }),
                    execute: async ({ latitude, longitude, location_name }) => {
                        return this.getWeather(latitude, longitude, location_name);
                    }
                },
                tell_joke: {
                    description: 'Tell a joke with a question-style setup and an answer punchline',
                    inputSchema: z.object({
                        setup: z.string().describe('The setup of the joke, usually in question form'),
                        punchline: z.string().describe('The punchline or answer to the joke')
                    }),
                    execute: async ({ setup, punchline }) => {
                        return this.tellJoke(setup, punchline);
                    }
                }
            }
        };
        try {
            const { text, toolResults } = await generateText(requestParams);
            this.debugApiCall('Vercel AI SDK OTEL (OpenAI + Image Gen)', { ...requestParams, model: modelName }, { text, toolResults });
            const displayParts = [];
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
                        displayParts.push(this.formatToolResult('get_weather', result.output));
                    }
                    else if (result.toolName === 'tell_joke' && 'output' in result) {
                        displayParts.push(this.formatToolResult('tell_joke', result.output));
                    }
                }
            }
            return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
        }
        catch (error) {
            console.error('Error in Vercel AI OTEL OpenAI + image gen chat:', error);
            throw new Error(`Vercel AI OTEL OpenAI + Image Gen Provider error: ${error.message}`);
        }
    }
}
//# sourceMappingURL=vercel-ai-otel-openai-image.js.map