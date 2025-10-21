import { PostHog } from "posthog-node";
import {
  WEATHER_TEMP_MIN_CELSIUS,
  WEATHER_TEMP_MAX_CELSIUS,
} from "./constants.js";

export interface Message {
  role: string;
  content?: any;
  tool_calls?: any[];
}

export interface Tool {
  name?: string;
  type?: string;
  description?: string;
  parameters?: any;
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
  protected debugMode: boolean;
  protected aiSessionId: string | null;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    this.posthogClient = posthogClient;
    this.aiSessionId = aiSessionId;
    this.debugMode = process.env.DEBUG === '1';
    this.initializeTools();
  }

  protected getPostHogProperties(): Record<string, any> {
    return this.aiSessionId ? { $ai_session_id: this.aiSessionId } : {};
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
    // Generate random temperature using configured range
    const range = WEATHER_TEMP_MAX_CELSIUS - WEATHER_TEMP_MIN_CELSIUS + 1;
    const tempCelsius = Math.floor(Math.random() * range) + WEATHER_TEMP_MIN_CELSIUS;
    const tempFahrenheit = Math.floor(tempCelsius * 9/5 + 32);
    return `The current weather in ${location} is ${tempCelsius}°C (${tempFahrenheit}°F) with partly cloudy skies and light winds.`;
  }

  protected formatToolResult(toolName: string, result: string): string {
    if (toolName === "get_weather") {
      return `🌤️  Weather: ${result}`;
    }

    return result;
  }

  protected debugLog(title: string, data: any, truncate: boolean = true): void {
    if (!this.debugMode) {
      return;
    }

    console.log("\n" + "=".repeat(80));
    console.log(`🐛 DEBUG: ${title}`);
    console.log("=".repeat(80));

    let output: string;
    if (typeof data === "object") {
      output = JSON.stringify(data, null, 2);
    } else {
      output = String(data);
    }

    // Truncate very long outputs
    if (truncate && output.length > 5000) {
      output = output.substring(0, 5000) + "\n... (truncated)";
    }

    console.log(output);
    console.log("=".repeat(80) + "\n");
  }

  protected debugApiCall(
    providerName: string,
    requestData: any,
    responseData?: any,
  ): void {
    /**
     * Simplified debug logging for API calls.
     * Just pass the request and optionally response objects - they'll be converted to JSON automatically.
     *
     * Usage:
     *   // Log request only (before API call)
     *   this.debugApiCall("Anthropic", requestParams);
     *
     *   // Log both request and response (after API call)
     *   this.debugApiCall("Anthropic", requestParams, response);
     */
    if (!this.debugMode) {
      return;
    }

    // Convert objects to plain objects for JSON serialization
    const toPlainObject = (obj: any): any => {
      if (obj === null || obj === undefined) {
        return obj;
      }
      if (typeof obj !== "object") {
        return obj;
      }
      if (Array.isArray(obj)) {
        return obj.map(toPlainObject);
      }
      // Try to convert to plain object
      if (obj.toJSON) {
        return obj.toJSON();
      }
      // For regular objects, recursively convert
      const result: any = {};
      for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
          result[key] = toPlainObject(obj[key]);
        }
      }
      return result;
    };

    this.debugLog(`${providerName} API Request`, toPlainObject(requestData));

    if (responseData !== undefined) {
      this.debugLog(
        `${providerName} API Response`,
        toPlainObject(responseData),
      );
    }
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
