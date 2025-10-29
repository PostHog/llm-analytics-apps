import { GoogleGenAI as PostHogGoogleGenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { StreamingProvider, Tool } from './base.js';
import { GEMINI_MODEL, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';

export class GeminiStreamingProvider extends StreamingProvider {
  private client: any;
  private history: any[] = [];
  private config: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.client = new PostHogGoogleGenAI({
      apiKey: process.env.GEMINI_API_KEY!,
      // vertexai: true,
      // project: "project-id",
      // location: "us-central1",
      posthog: posthogClient
    });
    
    this.config = {
      tools: this.tools
    };
  }

  protected getToolDefinitions(): Tool[] {
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
    }] as any;
  }

  getName(): string {
    return 'Google Gemini Streaming';
  }

  resetConversation(): void {
    this.history = [];
  }

  async *chatStream(
    userInput: string,
    base64Image?: string,
  ): AsyncGenerator<string, void, unknown> {
    // Build content parts for this message
    let parts: any[];
    
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
    } else {
      // Text-only content
      parts = [{ text: userInput }];
    }
    
    // Add user message to history
    this.history.push({
      role: 'user',
      parts: parts
    });

    // Create the streaming response
    const requestParams = {
      model: GEMINI_MODEL,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      posthogProperties: {
        $ai_span_name: "gemini_generate_content_streaming",
        ...this.getPostHogProperties(),
      },
      contents: this.history,
      config: this.config
    };

    if (this.debugMode) {
      this.debugLog("Google Gemini Streaming API Request", requestParams);
    }

    const stream = await this.client.models.generateContentStream(requestParams);

    let accumulatedText = "";
    const modelParts: any[] = [];
    const toolResults: string[] = [];

    // Process the stream
    for await (const chunk of stream) {
      // Handle text chunks
      if (chunk.candidates) {
        for (const candidate of chunk.candidates) {
          if (candidate.content) {
            for (const part of candidate.content.parts) {
              if (part.text) {
                // Yield only the delta text
                const delta = part.text;
                accumulatedText += delta;
                yield delta;
              } else if (part.functionCall) {
                // Handle function calls during streaming
                const functionCall = part.functionCall;
                
                if (functionCall.name === 'get_current_weather') {
                  const latitude = functionCall.args?.latitude || 0.0;
                  const longitude = functionCall.args?.longitude || 0.0;
                  const locationName = functionCall.args?.location_name;
                  const weatherResult = await this.getWeather(latitude, longitude, locationName);
                  const toolResultText = this.formatToolResult('get_weather', weatherResult);
                  toolResults.push(toolResultText);

                  // Yield the tool result to the stream
                  yield '\n\n' + toolResultText;

                  // Track the function call for history
                  modelParts.push({ functionCall });
                } else if (functionCall.name === 'tell_joke') {
                  const setup = functionCall.args?.setup || '';
                  const punchline = functionCall.args?.punchline || '';
                  const jokeResult = this.tellJoke(setup, punchline);
                  const toolResultText = this.formatToolResult('tell_joke', jokeResult);
                  toolResults.push(toolResultText);

                  // Yield the tool result to the stream
                  yield '\n\n' + toolResultText;

                  // Track the function call for history
                  modelParts.push({ functionCall });
                }
              }
            }
          }
        }
      }
    }

    // Build model parts for history
    if (accumulatedText) {
      modelParts.push({ text: accumulatedText });
    }

    // Add model response to history
    if (modelParts.length > 0) {
      this.history.push({
        role: 'model',
        parts: modelParts
      });
    }

    // Debug: Log the completed stream response
    if (this.debugMode) {
      this.debugLog("Google Gemini Streaming API Response (completed)", {
        accumulatedText: accumulatedText,
        modelParts: modelParts,
        toolResults: toolResults
      });
    }

    // Add tool results to history if any
    for (const toolResult of toolResults) {
      this.history.push({
        role: 'model',
        parts: [{ text: `Tool result: ${toolResult}` }]
      });
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