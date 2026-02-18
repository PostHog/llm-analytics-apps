// @ts-nocheck
import { GoogleGenAI as PostHogGoogleGenAI } from '@posthog/ai';
import { BaseProvider } from './base.js';
import { GEMINI_MODEL, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';
export class GeminiProvider extends BaseProvider {
    client;
    history = [];
    config;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.client = new PostHogGoogleGenAI({
            apiKey: process.env.GEMINI_API_KEY,
            // vertexai: true,
            // project: "project-id",
            // location: "us-central1",
            posthog: posthogClient
        });
        this.config = {
            tools: this.tools
        };
    }
    getToolDefinitions() {
        const weatherFunction = {
            name: 'get_current_weather',
            description: 'Gets the current weather for a given location.',
            parameters: {
                type: 'object',
                properties: {
                    latitude: {
                        type: 'number',
                        description: 'The latitude of the location (e.g., 37.7749 for San Francisco)',
                    },
                    longitude: {
                        type: 'number',
                        description: 'The longitude of the location (e.g., -122.4194 for San Francisco)',
                    },
                    location_name: {
                        type: 'string',
                        description: 'A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')',
                    },
                },
                required: ['latitude', 'longitude', 'location_name'],
            },
        };
        const jokeFunction = {
            name: 'tell_joke',
            description: 'Tell a joke with a question-style setup and an answer punchline',
            parameters: {
                type: 'object',
                properties: {
                    setup: {
                        type: 'string',
                        description: 'The setup of the joke, usually in question form',
                    },
                    punchline: {
                        type: 'string',
                        description: 'The punchline or answer to the joke',
                    },
                },
                required: ['setup', 'punchline'],
            },
        };
        return [{
                functionDeclarations: [weatherFunction, jokeFunction]
            }];
    }
    getName() {
        return 'Google Gemini';
    }
    resetConversation() {
        this.history = [];
    }
    async chat(userInput, base64Image) {
        // Build content parts for this message
        let parts;
        if (base64Image) {
            // Use native Gemini format for images
            parts = [
                { text: userInput },
                {
                    inlineData: {
                        mimeType: 'image/png',
                        data: base64Image
                    }
                }
            ];
        }
        else {
            // Text-only content
            parts = [{ text: userInput }];
        }
        // Add user message to history
        this.history.push({
            role: 'user',
            parts: parts
        });
        const requestParams = {
            model: GEMINI_MODEL,
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            posthogProperties: {
                $ai_span_name: "gemini_generate_content",
                ...this.getPostHogProperties(),
            },
            contents: this.history,
            config: this.config
        };
        const message = await this.client.models.generateContent(requestParams);
        this.debugApiCall("Google Gemini", requestParams, message);
        const displayParts = [];
        const modelParts = [];
        const toolResults = [];
        if (message.candidates) {
            for (const candidate of message.candidates) {
                if (candidate.content) {
                    for (const part of candidate.content.parts) {
                        if (part.functionCall) {
                            const functionCall = part.functionCall;
                            modelParts.push({ functionCall });
                            if (functionCall.name === 'get_current_weather') {
                                const latitude = functionCall.args?.latitude || 0.0;
                                const longitude = functionCall.args?.longitude || 0.0;
                                const locationName = functionCall.args?.location_name;
                                const weatherResult = await this.getWeather(latitude, longitude, locationName);
                                const toolResultText = this.formatToolResult('get_weather', weatherResult);
                                toolResults.push(toolResultText);
                                displayParts.push(toolResultText);
                            }
                            else if (functionCall.name === 'tell_joke') {
                                const setup = functionCall.args?.setup || '';
                                const punchline = functionCall.args?.punchline || '';
                                const jokeResult = this.tellJoke(setup, punchline);
                                const toolResultText = this.formatToolResult('tell_joke', jokeResult);
                                toolResults.push(toolResultText);
                                displayParts.push(toolResultText);
                            }
                        }
                        else if (part.text) {
                            modelParts.push({ text: part.text });
                            displayParts.push(part.text);
                        }
                    }
                }
            }
        }
        // Add model response to history
        if (modelParts.length > 0) {
            this.history.push({
                role: 'model',
                parts: modelParts
            });
        }
        for (const toolResult of toolResults) {
            this.history.push({
                role: 'model',
                parts: [{ text: `Tool result: ${toolResult}` }]
            });
        }
        return displayParts.length > 0 ? displayParts.join('\n\n') : (message.text || 'No response received');
    }
}
//# sourceMappingURL=gemini.js.map