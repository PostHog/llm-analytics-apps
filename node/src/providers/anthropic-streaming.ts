import { Anthropic as PostHogAnthropic } from "@posthog/ai";
import { PostHog } from "posthog-node";
import { StreamingProvider, Message, Tool } from "./base.js";
import { 
  ANTHROPIC_MODEL, 
  DEFAULT_MAX_TOKENS, 
  DEFAULT_POSTHOG_DISTINCT_ID,
  DEFAULT_THINKING_ENABLED,
  DEFAULT_THINKING_BUDGET_TOKENS
} from "./constants.js";

export class AnthropicStreamingProvider extends StreamingProvider {
  private client: any;
  private enableThinking: boolean;
  private thinkingBudget: number;

  constructor(posthogClient: PostHog, enableThinking: boolean = false, thinkingBudget?: number) {
    super(posthogClient);
    this.client = new PostHogAnthropic({
      apiKey: process.env.ANTHROPIC_API_KEY!,
      posthog: posthogClient,
    });
    this.enableThinking = enableThinking;
    this.thinkingBudget = thinkingBudget || DEFAULT_THINKING_BUDGET_TOKENS;
  }

  protected getToolDefinitions(): Tool[] {
    return [
      {
        name: "get_weather",
        description: "Get the current weather for a specific location",
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
    ];
  }

  getName(): string {
    return "Anthropic Streaming";
  }

  async *chatStream(
    userInput: string,
    base64Image?: string,
  ): AsyncGenerator<string, void, unknown> {
    let userContent: any;

    if (base64Image) {
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
    } else {
      userContent = userInput;
    }

    const userMessage: Message = {
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
    
    const requestParams: any = {
      model: ANTHROPIC_MODEL,
      max_tokens: maxTokens,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      posthogProperties: {
        $ai_span_name: "anthropic_messages_streaming",
      },
      tools: this.tools,
      messages: this.messages,
      stream: true,
    };

    // Add extended thinking if enabled
    if (this.enableThinking) {
      requestParams.thinking = {
        type: "enabled",
        budget_tokens: thinkingBudget,
      };
    }

    if (this.debugMode) {
      this.debugLog("Anthropic Streaming API Request", requestParams);
    }

    const stream = await this.client.messages.create(requestParams);

    let accumulatedContent = "";
    const assistantContent: any[] = [];
    const toolsUsed: any[] = [];
    let currentTextBlock: any = null;
    let currentThinkingBlock: any = null;

    for await (const chunk of stream) {
      // Handle content block start events
      if (chunk.type === "content_block_start") {
        if (chunk.content_block?.type === "thinking") {
          // Start a new thinking content block
          if (this.enableThinking) {
            yield "\n\n💭 Thinking: ";
          }
          currentThinkingBlock = {
            type: "thinking",
            thinking: "",
          };
          assistantContent.push(currentThinkingBlock);
          currentTextBlock = null;
        } else if (chunk.content_block?.type === "text") {
          // Start a new text content block
          // If we just had thinking, add some spacing
          if (currentThinkingBlock && this.enableThinking) {
            yield "\n\n";
          }
          currentTextBlock = {
            type: "text",
            text: "",
          };
          assistantContent.push(currentTextBlock);
          currentThinkingBlock = null;
        } else if (chunk.content_block?.type === "tool_use") {
          const toolInfo = {
            id: chunk.content_block.id,
            name: chunk.content_block.name,
            input: {},
          };
          toolsUsed.push(toolInfo);
          
          // Add tool use to assistant content immediately
          assistantContent.push({
            type: "tool_use",
            id: toolInfo.id,
            name: toolInfo.name,
            input: toolInfo.input, // Will be updated later
          });
          currentTextBlock = null;
          currentThinkingBlock = null;
        }
      }

      // Handle delta events (text, thinking, tool input)
      if ("delta" in chunk) {
        if ("thinking" in chunk.delta) {
          const thinkingDelta = chunk.delta.thinking ?? "";
          if (currentThinkingBlock) {
            currentThinkingBlock.thinking += thinkingDelta;
          }
          // Only yield thinking if enabled
          if (this.enableThinking) {
            yield thinkingDelta;
          }
        } else if ("text" in chunk.delta) {
          const delta = chunk.delta.text ?? "";
          accumulatedContent += delta;
          yield delta;
          // Update the current text block if we're tracking one
          if (currentTextBlock) {
            currentTextBlock.text += delta;
          }
        }
      }

      if (
        chunk.type === "content_block_delta" &&
        chunk.delta?.type === "input_json_delta"
      ) {
        const lastTool = toolsUsed[toolsUsed.length - 1];
        if (lastTool) {
          // Accumulate the JSON input
          if (!lastTool.inputString) {
            lastTool.inputString = "";
          }
          lastTool.inputString += chunk.delta.partial_json || "";
        }
      }

      if (chunk.type === "content_block_stop") {
        currentTextBlock = null; // Reset current text block
        currentThinkingBlock = null; // Reset current thinking block
        
        if (toolsUsed.length > 0) {
          const lastTool = toolsUsed[toolsUsed.length - 1];
          if (lastTool && lastTool.inputString) {
            try {
              lastTool.input = JSON.parse(lastTool.inputString);
              delete lastTool.inputString;

              // Update the input in assistant content
              // Find the corresponding tool_use in assistantContent and update its input
              for (const content of assistantContent) {
                if (content.type === "tool_use" && content.id === lastTool.id) {
                  content.input = lastTool.input;
                  break;
                }
              }

              // Execute the tool
              if (lastTool.name === "get_weather") {
                const latitude = lastTool.input.latitude || 0.0;
                const longitude = lastTool.input.longitude || 0.0;
                const locationName = lastTool.input.location_name;
                const weatherResult = await this.getWeather(latitude, longitude, locationName);
                const toolResultText = this.formatToolResult(
                  "get_weather",
                  weatherResult,
                );
                yield "\n\n" + toolResultText;
              }
            } catch (e) {
              console.error("Error parsing tool input:", e);
            }
          }
        }
      }
    }

    // Save assistant message
    const assistantMessage: Message = {
      role: "assistant",
      content: assistantContent.length > 0 ? assistantContent : [{type: "text", text: accumulatedContent || ""}],
    };
    this.messages.push(assistantMessage);

    // Debug: Log the completed stream response
    if (this.debugMode) {
      this.debugLog("Anthropic Streaming API Response (completed)", {
        accumulatedContent: accumulatedContent,
        assistantContent: assistantContent,
        toolsUsed: toolsUsed
      });
    }

    // If tools were used, add tool results to messages
    for (const tool of toolsUsed) {
      if (tool.name === "get_weather") {
        const latitude = tool.input.latitude || 0.0;
        const longitude = tool.input.longitude || 0.0;
        const locationName = tool.input.location_name;
        const weatherResult = await this.getWeather(latitude, longitude, locationName);

        const toolResultMessage: Message = {
          role: "user",
          content: [
            {
              type: "tool_result",
              tool_use_id: tool.id,
              content: weatherResult,
            },
          ],
        };
        this.messages.push(toolResultMessage);
      }
    }
  }

  // Non-streaming chat for compatibility
  async chat(userInput: string, base64Image?: string): Promise<string> {
    const chunks: string[] = [];
    for await (const chunk of this.chatStream(userInput, base64Image)) {
      chunks.push(chunk);
    }
    return chunks.join("");
  }
}
