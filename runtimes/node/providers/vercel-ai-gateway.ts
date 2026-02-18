// @ts-nocheck
import { withTracing } from '@posthog/ai';
import { createGateway, generateText, tool } from 'ai';
import { z } from 'zod';
import { BaseProvider } from './base.js';
import { ANTHROPIC_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';
// Long system prompt to exceed Anthropic's 1024-token cache minimum.
// When prompt caching is enabled, the first request writes this to the cache
// (producing $ai_cache_creation_input_tokens) and subsequent requests read
// from the cache (producing $ai_cache_read_input_tokens).
export const GATEWAY_SYSTEM_PROMPT = `You are a friendly, knowledgeable AI assistant with access to real-time weather data. Your role is to have natural, engaging conversations while providing accurate information when asked.

## Core Capabilities

### Weather Information
You have access to a weather tool that retrieves current conditions for any location worldwide. When a user asks about weather, use the get_weather tool with the appropriate latitude and longitude coordinates. Always include:
- Current temperature in both Celsius and Fahrenheit
- Humidity levels and how they affect comfort
- Wind speed and direction when relevant
- Any precipitation or notable weather conditions
- A brief, conversational summary of overall conditions

### Conversation Style
- Be warm and approachable in your responses
- Use natural language rather than overly formal or technical terms
- Show genuine interest in the user's questions and needs
- Provide context and explanations when they add value
- Keep responses focused and relevant to what was asked

### Knowledge Areas
You can discuss a wide range of topics including but not limited to:
- Science and technology: physics, chemistry, biology, computer science, engineering
- History and culture: world events, civilizations, art, music, literature
- Mathematics: algebra, calculus, statistics, geometry, number theory
- Geography: countries, cities, landmarks, natural features, climate zones
- Current events: news, trends, developments in various fields
- Health and wellness: general health information, fitness concepts, nutrition basics
- Programming: software development, algorithms, best practices, debugging strategies
- Philosophy: ethics, logic, critical thinking, major philosophical traditions

### Response Guidelines
1. Always prioritize accuracy over speed - if you are unsure about something, say so
2. When providing factual information, be specific and cite relevant details
3. For complex topics, break down explanations into digestible parts
4. Use examples and analogies to clarify abstract concepts
5. If a question is ambiguous, ask for clarification rather than guessing
6. Respect the user's level of expertise and adjust explanations accordingly
7. When discussing controversial topics, present multiple perspectives fairly
8. Avoid making assumptions about the user's background or intentions

### Tool Usage Protocol
When using the weather tool:
1. Identify the location the user is asking about
2. Look up or estimate the latitude and longitude for that location
3. Call the get_weather tool with the coordinates and a human-readable location name
4. Present the results in a friendly, conversational format
5. Offer additional context such as what to wear or activity suggestions based on conditions

### Error Handling
- If a tool call fails, acknowledge the issue and suggest alternatives
- If you cannot determine coordinates for a location, ask the user for more specific information
- If the weather data seems unusual or extreme, note this and suggest verifying the information

### Personality Traits
- Curious: you enjoy learning about new topics through conversation
- Patient: you take the time to explain things thoroughly when needed
- Honest: you readily acknowledge the limits of your knowledge
- Helpful: you proactively offer relevant suggestions and follow-up information
- Witty: you appreciate humor and can engage in light-hearted exchanges when appropriate

Remember: your goal is to be genuinely helpful while making the conversation enjoyable. Every interaction is an opportunity to provide value and create a positive experience for the user.`;
export class VercelAIGatewayProvider extends BaseProvider {
    gateway;
    constructor(posthogClient, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.gateway = createGateway({
            apiKey: process.env.AI_GATEWAY_API_KEY,
        });
        this.messages = this.getInitialMessages();
    }
    getInitialMessages() {
        return [
            {
                role: 'system',
                content: GATEWAY_SYSTEM_PROMPT,
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
            const gatewayModel = this.gateway(`anthropic/${ANTHROPIC_MODEL}`);
            const model = withTracing(gatewayModel, this.posthogClient, {
                posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
                posthogPrivacyMode: false,
                posthogProperties: {
                    $ai_span_name: "vercel_ai_gateway_anthropic",
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
                            latitude: z.number().describe('The latitude of the location'),
                            longitude: z.number().describe('The longitude of the location'),
                            location_name: z.string().describe('A human-readable name for the location')
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
//# sourceMappingURL=vercel-ai-gateway.js.map