// @ts-nocheck
import { withTracing } from '@posthog/ai';
import { createGateway, streamText, tool } from 'ai';
import { z } from 'zod';
import { StreamingProvider } from './base.js';
import { GATEWAY_ANTHROPIC_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_CACHEABLE } from './constants.js';
export class VercelAIGatewayAnthropicStreamingProvider extends StreamingProvider {
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
        return 'Vercel AI Gateway Streaming (Anthropic)';
    }
    async *chatStream(userInput, base64Image) {
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
        const model = withTracing(this.gatewayClient(GATEWAY_ANTHROPIC_MODEL), this.posthogClient, {
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            posthogPrivacyMode: false,
            posthogProperties: {
                $ai_span_name: "vercel_ai_gateway_stream_text_anthropic",
                ...this.getPostHogProperties(),
            },
        });
        try {
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
            if (this.debugMode) {
                this.debugLog("Vercel AI Gateway Streaming (Anthropic) API Request", requestParams);
            }
            const result = await streamText(requestParams);
            let accumulatedContent = '';
            const toolCalls = [];
            let currentToolCall = null;
            for await (const part of result.fullStream) {
                if (part.type === 'text-delta') {
                    const delta = part.text || '';
                    accumulatedContent += delta;
                    yield delta;
                }
                if (part.type === 'tool-call') {
                    currentToolCall = {
                        toolName: part.toolName,
                        args: part.input || {}
                    };
                    toolCalls.push(currentToolCall);
                }
                if (part.type === 'tool-result') {
                    const toolResult = part;
                    if (toolResult.toolName === 'get_weather') {
                        const weatherResult = toolResult.output;
                        const toolResultText = this.formatToolResult('get_weather', weatherResult);
                        yield '\n\n' + toolResultText;
                    }
                    else if (toolResult.toolName === 'tell_joke') {
                        const jokeResult = toolResult.output;
                        const toolResultText = this.formatToolResult('tell_joke', jokeResult);
                        yield '\n\n' + toolResultText;
                    }
                }
            }
            if (accumulatedContent) {
                const assistantMessage = {
                    role: 'assistant',
                    content: accumulatedContent
                };
                this.messages.push(assistantMessage);
            }
            else if (toolCalls.length > 0) {
                let toolResultsText = '';
                for (const tc of toolCalls) {
                    if (tc.toolName === 'get_weather') {
                        const latitude = tc.args.latitude || 0.0;
                        const longitude = tc.args.longitude || 0.0;
                        const locationName = tc.args.location_name;
                        const weatherResult = await this.getWeather(latitude, longitude, locationName);
                        toolResultsText += this.formatToolResult('get_weather', weatherResult);
                    }
                    else if (tc.toolName === 'tell_joke') {
                        const setup = tc.args.setup || '';
                        const punchline = tc.args.punchline || '';
                        const jokeResult = this.tellJoke(setup, punchline);
                        toolResultsText += this.formatToolResult('tell_joke', jokeResult);
                    }
                }
                if (toolResultsText) {
                    const assistantMessage = {
                        role: 'assistant',
                        content: toolResultsText
                    };
                    this.messages.push(assistantMessage);
                }
            }
            if (this.debugMode) {
                this.debugLog("Vercel AI Gateway Streaming (Anthropic) API Response (completed)", {
                    accumulatedContent: accumulatedContent,
                    toolCalls: toolCalls
                });
            }
        }
        catch (error) {
            console.error('Error in Vercel AI Gateway Anthropic streaming chat:', error);
            throw new Error(`Vercel AI Gateway Anthropic Streaming Provider error: ${error.message}`);
        }
    }
    async chat(userInput, base64Image) {
        const chunks = [];
        for await (const chunk of this.chatStream(userInput, base64Image)) {
            chunks.push(chunk);
        }
        return chunks.join('');
    }
}
//# sourceMappingURL=vercel-ai-gateway-anthropic-streaming.js.map