import { Anthropic as PostHogAnthropic } from "@posthog/ai";
import { PostHog } from "posthog-node";
import { BaseProvider, Message, Tool } from "./base.js";

export class AnthropicProvider extends BaseProvider {
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
    return "Anthropic";
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    let userContent: any;

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
    } else {
      userContent = userInput;
    }

    const userMessage: Message = {
      role: "user",
      content: userContent,
    };
    this.messages.push(userMessage);

    const message = await this.client.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 200,
      temperature: 0.7,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || "user-hog",
      tools: this.tools,
      messages: this.messages,
    });

    const assistantContent: any[] = [];
    const toolResults: string[] = [];
    const displayParts: string[] = [];

    if (message.content && message.content.length > 0) {
      for (const contentBlock of message.content) {
        if (contentBlock.type === "tool_use") {
          assistantContent.push(contentBlock);

          const toolName = contentBlock.name;
          const toolInput = contentBlock.input;

          if (toolName === "get_weather") {
            const location = toolInput.location || "unknown";
            const weatherResult = this.getWeather(location);
            const toolResultText = this.formatToolResult(
              "get_weather",
              weatherResult,
            );
            toolResults.push(toolResultText);
            displayParts.push(toolResultText);
          }
        } else if (contentBlock.type === "text") {
          assistantContent.push(contentBlock);
          displayParts.push(contentBlock.text);
        }
      }
    }

    const assistantMessage: Message = {
      role: "assistant",
      content: assistantContent,
    };
    this.messages.push(assistantMessage);

    if (toolResults.length > 0) {
      for (const contentBlock of message.content) {
        if (contentBlock.type === "tool_use") {
          const toolResultMessage: Message = {
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
