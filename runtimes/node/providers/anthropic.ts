// @ts-nocheck
import { Anthropic as PostHogAnthropic } from "@posthog/ai";
import { BaseProvider } from "./base.js";
import { ANTHROPIC_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, DEFAULT_THINKING_BUDGET_TOKENS, } from "./constants.js";
export class AnthropicProvider extends BaseProvider {
    client;
    enableThinking;
    thinkingBudget;
    constructor(posthogClient, enableThinking = false, thinkingBudget, aiSessionId = null) {
        super(posthogClient, aiSessionId);
        this.client = new PostHogAnthropic({
            apiKey: process.env.ANTHROPIC_API_KEY,
            posthog: posthogClient,
        });
        this.enableThinking = enableThinking;
        this.thinkingBudget = thinkingBudget || DEFAULT_THINKING_BUDGET_TOKENS;
    }
    getToolDefinitions() {
        return [
            {
                name: "get_weather",
                description: "Get the current weather for a specific location using geographical coordinates",
                input_schema: {
                    type: "object",
                    properties: {
                        latitude: {
                            type: "number",
                            description: "The latitude of the location (e.g., 37.7749 for San Francisco)",
                        },
                        longitude: {
                            type: "number",
                            description: "The longitude of the location (e.g., -122.4194 for San Francisco)",
                        },
                        location_name: {
                            type: "string",
                            description: "A human-readable name for the location (e.g., 'San Francisco, CA' or 'Dublin, Ireland')",
                        },
                    },
                    required: ["latitude", "longitude", "location_name"],
                },
            },
            {
                name: "tell_joke",
                description: "Tell a joke with a question-style setup and an answer punchline",
                input_schema: {
                    type: "object",
                    properties: {
                        setup: {
                            type: "string",
                            description: "The setup of the joke, usually in question form",
                        },
                        punchline: {
                            type: "string",
                            description: "The punchline or answer to the joke",
                        },
                    },
                    required: ["setup", "punchline"],
                },
            },
        ];
    }
    getName() {
        return "Anthropic";
    }
    async chat(userInput, base64Image) {
        let userContent;
        if (base64Image) {
            // For image input, create content array with text and image
            userContent = [
                { type: "text", text: userInput },
                {
                    type: "image",
                    source: {
                        type: "base64",
                        media_type: "image/png",
                        data: base64Image,
                    },
                },
            ];
        }
        else {
            userContent = userInput;
        }
        const userMessage = {
            role: "user",
            content: userContent,
        };
        this.messages.push(userMessage);
        // Prepare API request parameters
        // Note: max_tokens must be greater than thinking.budget_tokens
        const thinkingBudget = this.enableThinking ? Math.max(this.thinkingBudget, 1024) : 0;
        const maxTokens = this.enableThinking
            ? Math.max(DEFAULT_MAX_TOKENS, thinkingBudget + 2000)
            : DEFAULT_MAX_TOKENS;
        const requestParams = {
            model: ANTHROPIC_MODEL,
            max_tokens: maxTokens,
            posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
            posthogProperties: {
                $ai_span_name: "anthropic_messages",
                ...this.getPostHogProperties(),
            },
            tools: this.tools,
            messages: this.messages,
        };
        // Add extended thinking if enabled
        if (this.enableThinking) {
            requestParams.thinking = {
                type: "enabled",
                budget_tokens: thinkingBudget,
            };
        }
        const message = await this.client.messages.create(requestParams);
        // Debug: Log the API call (request + response)
        this.debugApiCall("Anthropic", requestParams, message);
        const assistantContent = [];
        const toolResults = [];
        const displayParts = [];
        if (message.content && message.content.length > 0) {
            for (const contentBlock of message.content) {
                if (contentBlock.type === "thinking") {
                    // Store thinking block for message history
                    assistantContent.push(contentBlock);
                    // Display thinking content if enabled
                    if (this.enableThinking) {
                        displayParts.push(`💭 Thinking: ${contentBlock.thinking}`);
                    }
                }
                else if (contentBlock.type === "tool_use") {
                    assistantContent.push(contentBlock);
                    const toolName = contentBlock.name;
                    const toolInput = contentBlock.input;
                    if (toolName === "get_weather") {
                        const latitude = toolInput.latitude || 0.0;
                        const longitude = toolInput.longitude || 0.0;
                        const locationName = toolInput.location_name;
                        const weatherResult = await this.getWeather(latitude, longitude, locationName);
                        const toolResultText = this.formatToolResult("get_weather", weatherResult);
                        toolResults.push(toolResultText);
                        displayParts.push(toolResultText);
                    }
                    else if (toolName === "tell_joke") {
                        const setup = toolInput.setup || "";
                        const punchline = toolInput.punchline || "";
                        const jokeResult = this.tellJoke(setup, punchline);
                        const toolResultText = this.formatToolResult("tell_joke", jokeResult);
                        toolResults.push(toolResultText);
                        displayParts.push(toolResultText);
                    }
                }
                else if (contentBlock.type === "text") {
                    assistantContent.push(contentBlock);
                    displayParts.push(contentBlock.text);
                }
            }
        }
        const assistantMessage = {
            role: "assistant",
            content: assistantContent,
        };
        this.messages.push(assistantMessage);
        if (toolResults.length > 0) {
            for (const contentBlock of message.content) {
                if (contentBlock.type === "tool_use") {
                    const toolResultMessage = {
                        role: "user",
                        content: [
                            {
                                type: "tool_result",
                                tool_use_id: contentBlock.id,
                                content: toolResults[0] || "Tool executed",
                            },
                        ],
                    };
                    this.messages.push(toolResultMessage);
                    break;
                }
            }
        }
        return displayParts.length > 0
            ? displayParts.join("\n\n")
            : "No response received";
    }
}
//# sourceMappingURL=anthropic.js.map