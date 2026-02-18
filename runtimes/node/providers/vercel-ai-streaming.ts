// @ts-nocheck
import { withTracing } from '@posthog/ai';
import { streamText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { StreamingProvider } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';
export class VercelAIStreamingProvider extends StreamingProvider {
    openaiClient;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.openaiClient = createOpenAI({
            apiKey: process.env.OPENAI_API_KEY
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
        // Vercel AI SDK doesn't use this, but we need to implement it
        return [];
    }
    getName() {
        return 'Vercel AI SDK Streaming (OpenAI)';
    }
    async *chatStream(userInput, base64Image) {
        let userContent;
        if (base64Image) {
            // For image input, create content array with text and image
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
        // Use vision model for images, regular model otherwise
        const modelName = base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL;
        const model = withTracing(this.openaiClient(modelName), this.posthogClient, {
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            posthogPrivacyMode: false,
            posthogProperties: {
                $ai_span_name: "vercel_ai_stream_text",
                ...this.getPostHogProperties(),
            },
        });
        try {
            const requestParams = {
                model: model,
                messages: this.messages,
                maxOutputTokens: DEFAULT_MAX_TOKENS,
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
            if (this.debugMode) {
                this.debugLog("Vercel AI SDK Streaming (OpenAI) API Request", requestParams);
            }
            const result = await streamText(requestParams);
            let accumulatedContent = '';
            const toolCalls = [];
            let currentToolCall = null;
            for await (const part of result.fullStream) {
                // Handle text delta events
                if (part.type === 'text-delta') {
                    const delta = part.text || '';
                    accumulatedContent += delta;
                    yield delta;
                }
                // Handle tool call start
                if (part.type === 'tool-call') {
                    currentToolCall = {
                        toolName: part.toolName,
                        args: part.input || {}
                    };
                    toolCalls.push(currentToolCall);
                }
                // Handle tool result
                if (part.type === 'tool-result') {
                    const toolResult = part;
                    if (toolResult.toolName === 'get_weather') {
                        // The tool was already executed via the execute function
                        // Format and yield the result
                        const weatherResult = toolResult.output;
                        const toolResultText = this.formatToolResult('get_weather', weatherResult);
                        yield '\n\n' + toolResultText;
                    }
                    else if (toolResult.toolName === 'tell_joke') {
                        // The tool was already executed via the execute function
                        // Format and yield the result
                        const jokeResult = toolResult.output;
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
                const assistantMessage = {
                    role: 'assistant',
                    content: accumulatedContent
                };
                this.messages.push(assistantMessage);
            }
            else if (toolCalls.length > 0) {
                // If there was a tool call but no text content, save the tool result as assistant message
                let toolResultsText = '';
                for (const toolCall of toolCalls) {
                    if (toolCall.toolName === 'get_weather') {
                        const latitude = toolCall.args.latitude || 0.0;
                        const longitude = toolCall.args.longitude || 0.0;
                        const locationName = toolCall.args.location_name;
                        const weatherResult = await this.getWeather(latitude, longitude, locationName);
                        toolResultsText += this.formatToolResult('get_weather', weatherResult);
                    }
                    else if (toolCall.toolName === 'tell_joke') {
                        const setup = toolCall.args.setup || '';
                        const punchline = toolCall.args.punchline || '';
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
            // Debug: Log the completed stream response
            if (this.debugMode) {
                this.debugLog("Vercel AI SDK Streaming (OpenAI) API Response (completed)", {
                    accumulatedContent: accumulatedContent,
                    toolCalls: toolCalls
                });
            }
        }
        catch (error) {
            console.error('Error in Vercel AI streaming chat:', error);
            throw new Error(`Vercel AI Streaming Provider error: ${error.message}`);
        }
    }
    // Non-streaming chat for compatibility
    async chat(userInput, base64Image) {
        const chunks = [];
        for await (const chunk of this.chatStream(userInput, base64Image)) {
            chunks.push(chunk);
        }
        return chunks.join('');
    }
}
//# sourceMappingURL=vercel-ai-streaming.js.map