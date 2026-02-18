// @ts-nocheck
import { withTracing } from '@posthog/ai';
import { createGateway, generateText, tool } from 'ai';
import { z } from 'zod';
import { BaseProvider } from './base.js';
import { GATEWAY_ANTHROPIC_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_CACHEABLE } from './constants.js';
export class VercelAIGatewayAnthropicProvider extends BaseProvider {
    gatewayClient;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.gatewayClient = createGateway({
            apiKey: process.env.AI_GATEWAY_API_KEY,
        });
        this.messages = this.getInitialMessages();
    }
    getInitialMessages() {
        return [
            {
                role: 'system',
                content: SYSTEM_PROMPT_CACHEABLE,
                // Enable Anthropic prompt caching on the system prompt.
                // The system prompt is >1024 tokens so it qualifies for caching.
                providerOptions: {
                    anthropic: {
                        cacheControl: { type: 'ephemeral' }
                    }
                }
            }
        ];
    }
    getToolDefinitions() {
        return [];
    }
    getName() {
        return 'Vercel AI Gateway (Anthropic)';
    }
    async chat(userInput, base64Image) {
        let userContent;
        if (base64Image) {
            userContent = [
                { type: 'text', text: userInput },
                {
                    type: 'image',
                    image: `data:image/png;base64,${base64Image}`
                }
            ];
        }
        else {
            userContent = userInput;
        }
        const userMessage = {
            role: 'user',
            content: userContent
        };
        this.messages.push(userMessage);
        const displayParts = [];
        try {
            const model = withTracing(this.gatewayClient(GATEWAY_ANTHROPIC_MODEL), this.posthogClient, {
                posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
                posthogPrivacyMode: false,
                posthogProperties: {
                    $ai_span_name: "vercel_ai_gateway_generate_text_anthropic",
                    ...this.getPostHogProperties(),
                },
            });
            const requestParams = {
                model: model,
                messages: this.messages,
                maxOutputTokens: DEFAULT_MAX_TOKENS,
                tools: {
                    get_weather: tool({
                        description: 'Get the current weather for a specific location',
                        inputSchema: z.object({
                            latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
                            longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
                            location_name: z.string().describe('A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')')
                        }),
                        execute: async ({ latitude, longitude, location_name }) => {
                            return this.getWeather(latitude, longitude, location_name);
                        }
                    }),
                    tell_joke: tool({
                        description: 'Tell a joke with a question-style setup and an answer punchline',
                        inputSchema: z.object({
                            setup: z.string().describe('The setup of the joke, usually in question form'),
                            punchline: z.string().describe('The punchline or answer to the joke')
                        }),
                        execute: async ({ setup, punchline }) => {
                            return this.tellJoke(setup, punchline);
                        }
                    })
                }
            };
            const { text, toolResults } = await generateText(requestParams);
            this.debugApiCall("Vercel AI Gateway (Anthropic)", requestParams, { text, toolResults });
            if (text) {
                displayParts.push(text);
                const assistantMessage = {
                    role: 'assistant',
                    content: text
                };
                this.messages.push(assistantMessage);
            }
            if (toolResults && toolResults.length > 0) {
                for (const result of toolResults) {
                    if (result.toolName === 'get_weather' && 'output' in result) {
                        const toolResultText = this.formatToolResult('get_weather', result.output);
                        displayParts.push(toolResultText);
                        const toolMessage = {
                            role: 'assistant',
                            content: toolResultText
                        };
                        this.messages.push(toolMessage);
                    }
                    else if (result.toolName === 'tell_joke' && 'output' in result) {
                        const toolResultText = this.formatToolResult('tell_joke', result.output);
                        displayParts.push(toolResultText);
                        const toolMessage = {
                            role: 'assistant',
                            content: toolResultText
                        };
                        this.messages.push(toolMessage);
                    }
                }
            }
            return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
        }
        catch (error) {
            console.error('Error in Vercel AI Gateway Anthropic chat:', error);
            throw new Error(`Vercel AI Gateway Anthropic Provider error: ${error.message}`);
        }
    }
}
//# sourceMappingURL=vercel-ai-gateway-anthropic.js.map