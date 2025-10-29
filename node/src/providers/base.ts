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

  protected async getWeather(
    latitude: number,
    longitude: number,
    locationName?: string
  ): Promise<string> {
    try {
      // Get weather data from Open-Meteo API
      const weatherUrl = "https://api.open-meteo.com/v1/forecast";
      const params = new URLSearchParams({
        latitude: latitude.toString(),
        longitude: longitude.toString(),
        current: "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        temperature_unit: "celsius",
        wind_speed_unit: "kmh",
        precipitation_unit: "mm",
      });

      const response = await fetch(`${weatherUrl}?${params}`);
      const data: any = await response.json();

      if (data.current) {
        const current: any = data.current;
        const tempCelsius = current.temperature_2m;
        const tempFahrenheit = (tempCelsius * 9 / 5 + 32).toFixed(1);
        const humidity = current.relative_humidity_2m;
        const feelsLike = current.apparent_temperature;
        const precipitation = current.precipitation;
        const windSpeed = current.wind_speed_10m;
        const weatherCode = current.weather_code;

        // Interpret WMO weather code
        const weatherDescriptions: { [key: number]: string } = {
          0: "clear skies",
          1: "mainly clear",
          2: "partly cloudy",
          3: "overcast",
          45: "foggy",
          48: "depositing rime fog",
          51: "light drizzle",
          53: "moderate drizzle",
          55: "dense drizzle",
          61: "slight rain",
          63: "moderate rain",
          65: "heavy rain",
          71: "slight snow",
          73: "moderate snow",
          75: "heavy snow",
          77: "snow grains",
          80: "slight rain showers",
          81: "moderate rain showers",
          82: "violent rain showers",
          85: "slight snow showers",
          86: "heavy snow showers",
          95: "thunderstorm",
          96: "thunderstorm with slight hail",
          99: "thunderstorm with heavy hail",
        };

        const weatherDesc =
          weatherDescriptions[weatherCode] || `weather code ${weatherCode}`;

        // Use location name if provided, otherwise fall back to coordinates
        const locationStr = locationName
          ? locationName
          : `coordinates (${latitude}, ${longitude})`;

        let result = `The current weather in ${locationStr} is ${tempCelsius}°C (${tempFahrenheit}°F) with ${weatherDesc}.`;

        if (feelsLike !== tempCelsius) {
          result += ` It feels like ${feelsLike}°C.`;
        }

        result += ` Humidity is ${humidity}%. Wind speed is ${windSpeed} km/h.`;

        if (precipitation > 0) {
          result += ` Precipitation: ${precipitation} mm.`;
        }

        return result;
      } else {
        return `Unable to fetch weather data for ${locationName || `coordinates (${latitude}, ${longitude})`}`;
      }
    } catch (error: any) {
      return `Error fetching weather: ${error?.message || "Unknown error"}`;
    }
  }

  protected tellJoke(setup: string, punchline: string): string {
    return `${setup}\n\n${punchline}`;
  }

  protected formatToolResult(toolName: string, result: string): string {
    if (toolName === "get_weather") {
      return `🌤️  Weather: ${result}`;
    } else if (toolName === "tell_joke") {
      return `😂 Joke: ${result}`;
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
