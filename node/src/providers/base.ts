import { PostHog } from "posthog-node";

export interface Message {
  role: string;
  content?: any;
  tool_calls?: any[];
}

export interface Tool {
  name?: string;
  type?: string;
  description?: string;
  input_schema?: any;
  function?: {
    name: string;
    description: string;
    parameters: any;
  };
}

export abstract class BaseProvider {
  protected posthogClient: PostHog;
  protected messages: Message[] = [];
  protected tools: Tool[] = [];

  constructor(posthogClient: PostHog) {
    this.posthogClient = posthogClient;
    this.initializeTools();
  }

  protected initializeTools(): void {
    // Default weather tool - can be overridden by subclasses
    this.tools = this.getToolDefinitions();
  }

  protected abstract getToolDefinitions(): Tool[];

  abstract getName(): string;

  abstract chat(userInput: string, base64Image?: string): Promise<string>;

  resetConversation(): void {
    this.messages = this.getInitialMessages();
  }

  protected getInitialMessages(): Message[] {
    return [];
  }

  protected getWeather(location: string): string {
    return `The current weather in ${location} is 22°C (72°F) with partly cloudy skies and light winds.`;
  }

  protected formatToolResult(toolName: string, result: string): string {
    if (toolName === "get_weather") {
      return `🌤️  Weather: ${result}`;
    }

    return result;
  }
}

export abstract class StreamingProvider extends BaseProvider {
  abstract chatStream(
    userInput: string,
    base64Image?: string,
  ): AsyncGenerator<string, void, unknown>;

  // Default implementation that just yields the full response at once
  async *defaultChatStream(
    userInput: string,
    base64Image?: string,
  ): AsyncGenerator<string, void, unknown> {
    const response = await this.chat(userInput, base64Image);
    yield response;
  }
}
