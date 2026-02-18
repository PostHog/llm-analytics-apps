// @ts-nocheck
import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { StreamingProvider } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, OPENAI_EMBEDDING_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';
export class OpenAIStreamingProvider extends StreamingProvider {
    client;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.client = new PostHogOpenAI({
            apiKey: process.env.OPENAI_API_KEY,
            posthog: posthogClient
        });
    }
    getToolDefinitions() {
        return [
            {
                type: 'function',
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
            },
            {
                type: 'function',
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
        ];
    }
    getName() {
        return 'OpenAI Responses Streaming';
    }
    async embed(text, model = OPENAI_EMBEDDING_MODEL) {
        const response = await this.client.embeddings.create({
            model: model,
            input: text,
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID
        });
        if (response.data && response.data.length > 0) {
            return response.data[0].embedding;
        }
        return [];
    }
    async *chatStream(userInput, base64Image) {
        let userMessage;
        if (base64Image) {
            // For image input, create content array with text and image
            userMessage = {
                role: 'user',
                content: [
                    {
                        type: 'input_text',
                        text: userInput
                    },
                    {
                        type: 'input_image',
                        image_url: `data:image/png;base64,${base64Image}`
                    }
                ]
            };
        }
        else {
            userMessage = {
                role: 'user',
                content: userInput
            };
        }
        this.messages.push(userMessage);
        const requestParams = {
            model: base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL,
            max_output_tokens: DEFAULT_MAX_TOKENS,
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            posthogProperties: {
                $ai_span_name: "openai_responses_streaming",
                ...this.getPostHogProperties(),
            },
            input: this.messages,
            instructions: SYSTEM_PROMPT_FRIENDLY,
            tools: this.tools,
            stream: true
        };
        if (this.debugMode) {
            this.debugLog("OpenAI Responses Streaming API Request", requestParams);
        }
        const stream = await this.client.responses.create(requestParams);
        let accumulatedContent = '';
        const finalOutput = [];
        const toolCalls = [];
        for await (const chunk of stream) {
            // Handle different streaming event types
            if (chunk.type === 'response.output_text.delta') {
                // Text delta streaming - this is the main text streaming event
                if (chunk.delta) {
                    accumulatedContent += chunk.delta;
                    yield chunk.delta;
                }
            }
            else if (chunk.type === 'response.output_item.added') {
                // Track when a function call starts
                if (chunk.item && chunk.item.type === 'function_call') {
                    // Store the function name for later use
                    if (!toolCalls[chunk.output_index]) {
                        toolCalls[chunk.output_index] = {
                            name: chunk.item.name || 'get_weather',
                            arguments: ''
                        };
                    }
                }
            }
            else if (chunk.type === 'response.function_call_arguments.done') {
                // Function call arguments completed
                if (chunk.arguments && chunk.output_index !== undefined) {
                    // Get the function info we stored earlier
                    const toolCall = toolCalls[chunk.output_index];
                    if (toolCall && toolCall.name === 'get_weather') {
                        let args = {};
                        try {
                            args = JSON.parse(chunk.arguments);
                        }
                        catch (e) {
                            args = {};
                        }
                        const latitude = args.latitude || 0.0;
                        const longitude = args.longitude || 0.0;
                        const locationName = args.location_name;
                        const weatherResult = await this.getWeather(latitude, longitude, locationName);
                        const toolResultText = this.formatToolResult('get_weather', weatherResult);
                        yield '\n\n' + toolResultText;
                        // Update the arguments
                        toolCall.arguments = chunk.arguments;
                    }
                    else if (toolCall && toolCall.name === 'tell_joke') {
                        let args = {};
                        try {
                            args = JSON.parse(chunk.arguments);
                        }
                        catch (e) {
                            args = {};
                        }
                        const setup = args.setup || '';
                        const punchline = args.punchline || '';
                        const jokeResult = this.tellJoke(setup, punchline);
                        const toolResultText = this.formatToolResult('tell_joke', jokeResult);
                        yield '\n\n' + toolResultText;
                        // Update the arguments
                        toolCall.arguments = chunk.arguments;
                    }
                }
            }
            else if (chunk.type === 'response.completed' && chunk.response) {
                // Response completed event - only handle content that wasn't already streamed
                if (chunk.response.output && chunk.response.output.length > 0) {
                    for (const outputItem of chunk.response.output) {
                        // Check if this is a content message that wasn't already streamed
                        if (outputItem.content && Array.isArray(outputItem.content)) {
                            // Only add content if we didn't stream it already
                            for (const contentItem of outputItem.content) {
                                if (contentItem.text && !accumulatedContent.includes(contentItem.text)) {
                                    accumulatedContent += contentItem.text;
                                    yield contentItem.text;
                                }
                            }
                        }
                        // Tool calls are already handled in response.function_call_arguments.done
                        // So we don't need to handle them here
                    }
                }
            }
        }
        // Save assistant message with accumulated content or tool results
        const assistantContentItems = [];
        // Add text content if any
        if (accumulatedContent) {
            assistantContentItems.push({
                type: 'output_text',
                text: accumulatedContent
            });
        }
        // Add tool results if any
        if (toolCalls.length > 0 && toolCalls.some(tc => tc.arguments)) {
            for (const toolCall of toolCalls) {
                if (toolCall.arguments && toolCall.name === 'get_weather') {
                    let args = {};
                    try {
                        args = JSON.parse(toolCall.arguments);
                    }
                    catch (e) {
                        args = {};
                    }
                    const latitude = args.latitude || 0.0;
                    const longitude = args.longitude || 0.0;
                    const locationName = args.location_name;
                    const weatherResult = await this.getWeather(latitude, longitude, locationName);
                    // Add tool result as output_text for conversation history
                    // For client-side history management, add as assistant message with output_text
                    assistantContentItems.push({
                        type: 'output_text',
                        text: weatherResult
                    });
                }
                else if (toolCall.arguments && toolCall.name === 'tell_joke') {
                    let args = {};
                    try {
                        args = JSON.parse(toolCall.arguments);
                    }
                    catch (e) {
                        args = {};
                    }
                    const setup = args.setup || '';
                    const punchline = args.punchline || '';
                    const jokeResult = this.tellJoke(setup, punchline);
                    // Add tool result as output_text for conversation history
                    // For client-side history management, add as assistant message with output_text
                    assistantContentItems.push({
                        type: 'output_text',
                        text: jokeResult
                    });
                }
            }
        }
        // Add to conversation history if there's any content
        if (assistantContentItems.length > 0) {
            const assistantMessage = {
                role: 'assistant',
                content: assistantContentItems
            };
            this.messages.push(assistantMessage);
        }
        // Debug: Log the completed stream response
        if (this.debugMode) {
            this.debugLog("OpenAI Responses Streaming API Response (completed)", {
                accumulatedContent: accumulatedContent,
                toolCalls: toolCalls,
                finalOutput: finalOutput
            });
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
//# sourceMappingURL=openai-streaming.js.map