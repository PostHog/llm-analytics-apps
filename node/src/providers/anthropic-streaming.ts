import { Anthropic as PostHogAnthropic } from "@posthog/ai";
import { PostHog } from "posthog-node";
import { StreamingProvider, Message, Tool } from "./base.js";

export class AnthropicStreamingProvider extends StreamingProvider {
  private client: any;

  constructor(posthogClient: PostHog) {
    super(posthogClient);
    this.client = new PostHogAnthropic({
      apiKey: process.env.ANTHROPIC_API_KEY!,
      posthog: posthogClient,
    });
  }

  protected getToolDefinitions(): Tool[] {
    return [
      {
        name: "get_weather",
        description: "Get the current weather for a specific location",
        input_schema: {
          type: "object",
          properties: {
            location: {
              type: "string",
              description: "The city or location name to get weather for",
            },
          },
          required: ["location"],
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

    const stream = await this.client.messages.create({
      model: "claude-3-5-haiku-latest",
      max_tokens: 200,
      temperature: 0.7,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || "user-hog",
      tools: this.tools,
      messages: this.messages,
      stream: true,
    });

    let accumulatedContent = "";
    const assistantContent: any[] = [];
    const toolsUsed: any[] = [];
    let currentTextBlock: any = null;

    for await (const chunk of stream) {
      // Handle content block start events
      if (chunk.type === "content_block_start") {
        if (chunk.content_block?.type === "text") {
          // Start a new text content block
          currentTextBlock = {
            type: "text",
            text: "",
          };
          assistantContent.push(currentTextBlock);
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
          currentTextBlock = null; // Not a text block
        }
      }

      // Handle text delta events
      if ("delta" in chunk) {
        if ("text" in chunk.delta) {
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
                const location = lastTool.input.location || "unknown";
                const weatherResult = this.getWeather(location);
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

    // If tools were used, add tool results to messages
    for (const tool of toolsUsed) {
      if (tool.name === "get_weather") {
        const location = tool.input.location || "unknown";
        const weatherResult = this.getWeather(location);

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
