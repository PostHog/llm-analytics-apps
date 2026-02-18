// @ts-nocheck
import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { BaseProvider } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, OPENAI_EMBEDDING_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY, } from './constants.js';
export class OpenAIChatProvider extends BaseProvider {
    client;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.client = new PostHogOpenAI({
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
        return [
            {
                type: 'function',
                function: {
                    name: 'get_weather',
                    description: 'Get the current weather for a specific location',
                    parameters: {
                        type: 'object',
                        properties: {
                            latitude: {
                                type: 'number',
                                description: 'The latitude of the location (e.g., 37.7749 for San Francisco)'
                            },
                            longitude: {
                                type: 'number',
                                description: 'The longitude of the location (e.g., -122.4194 for San Francisco)'
                            },
                            location_name: {
                                type: 'string',
                                description: 'A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')'
                            }
                        },
                        required: ['latitude', 'longitude', 'location_name']
                    }
                }
            },
            {
                type: 'function',
                function: {
                    name: 'tell_joke',
                    description: 'Tell a joke with a question-style setup and an answer punchline',
                    parameters: {
                        type: 'object',
                        properties: {
                            setup: {
                                type: 'string',
                                description: 'The setup of the joke, usually in question form'
                            },
                            punchline: {
                                type: 'string',
                                description: 'The punchline or answer to the joke'
                            }
                        },
                        required: ['setup', 'punchline']
                    }
                }
            }
        ];
    }
    getName() {
        return 'OpenAI Chat Completions';
    }
    async embed(text, model = OPENAI_EMBEDDING_MODEL) {
        const response = await this.client.embeddings.create({
            model: model,
            input: text
        });
        if (response.data && response.data.length > 0) {
            return response.data[0].embedding;
        }
        return [];
    }
    async chat(userInput, base64Image) {
        let userContent;
        if (base64Image) {
            // For image input, create content array with text and image
            userContent = [
                {
                    type: 'text',
                    text: userInput
                },
                {
                    type: 'image_url',
                    image_url: {
                        url: `data:image/png;base64,${base64Image}`
                    }
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
        const requestParams = {
            model: base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL, // Use vision model for images
            max_completion_tokens: DEFAULT_MAX_TOKENS,
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            posthogProperties: {
                $ai_span_name: "openai_chat_completions",
                ...this.getPostHogProperties(),
            },
            messages: this.messages,
            tools: this.tools,
            tool_choice: 'auto'
        };
        const response = await this.client.chat.completions.create(requestParams);
        this.debugApiCall("OpenAI Chat Completions", requestParams, response);
        const displayParts = [];
        let assistantContent = '';
        const choice = response.choices[0];
        const message = choice.message;
        if (message.content) {
            assistantContent = message.content;
            displayParts.push(message.content);
        }
        if (message.tool_calls) {
            for (const toolCall of message.tool_calls) {
                if (toolCall.function.name === 'get_weather') {
                    try {
                        const args = JSON.parse(toolCall.function.arguments);
                        const latitude = args.latitude || 0.0;
                        const longitude = args.longitude || 0.0;
                        const locationName = args.location_name;
                        const weatherResult = await this.getWeather(latitude, longitude, locationName);
                        const toolResultText = this.formatToolResult('get_weather', weatherResult);
                        displayParts.push(toolResultText);
                        this.messages.push({
                            role: 'assistant',
                            content: assistantContent,
                            tool_calls: [
                                {
                                    id: toolCall.id,
                                    type: 'function',
                                    function: {
                                        name: toolCall.function.name,
                                        arguments: toolCall.function.arguments
                                    }
                                }
                            ]
                        });
                        this.messages.push({
                            role: 'tool',
                            tool_call_id: toolCall.id,
                            content: weatherResult
                        });
                    }
                    catch (e) {
                        displayParts.push('❌ Error parsing tool arguments');
                    }
                }
                else if (toolCall.function.name === 'tell_joke') {
                    try {
                        const args = JSON.parse(toolCall.function.arguments);
                        const setup = args.setup || '';
                        const punchline = args.punchline || '';
                        const jokeResult = this.tellJoke(setup, punchline);
                        const toolResultText = this.formatToolResult('tell_joke', jokeResult);
                        displayParts.push(toolResultText);
                        this.messages.push({
                            role: 'assistant',
                            content: assistantContent,
                            tool_calls: [
                                {
                                    id: toolCall.id,
                                    type: 'function',
                                    function: {
                                        name: toolCall.function.name,
                                        arguments: toolCall.function.arguments
                                    }
                                }
                            ]
                        });
                        this.messages.push({
                            role: 'tool',
                            tool_call_id: toolCall.id,
                            content: jokeResult
                        });
                    }
                    catch (e) {
                        displayParts.push('❌ Error parsing tool arguments');
                    }
                }
            }
        }
        else {
            if (assistantContent) {
                const assistantMessage = {
                    role: 'assistant',
                    content: assistantContent
                };
                this.messages.push(assistantMessage);
            }
        }
        return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
    }
}
//# sourceMappingURL=openai-chat.js.map