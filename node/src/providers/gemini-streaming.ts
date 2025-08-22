import { GoogleGenAI as PostHogGoogleGenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { StreamingProvider, Tool } from './base.js';

export class GeminiStreamingProvider extends StreamingProvider {
  private client: any;
  private history: any[] = [];
  private config: any;

  constructor(posthogClient: PostHog) {
    super(posthogClient);
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
          location: {
            type: 'string',
            description: 'The city name, e.g. San Francisco',
          },
        },
        required: ['location'],
      },
    };

    return [{ 
      functionDeclarations: [weatherFunction] 
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
    const stream = await this.client.models.generateContentStream({
      model: 'gemini-2.5-flash',
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || 'user-hog',
      contents: this.history,
      config: this.config
    });

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
                  const location = functionCall.args?.location || 'unknown';
                  const weatherResult = this.getWeather(location);
                  const toolResultText = this.formatToolResult('get_weather', weatherResult);
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