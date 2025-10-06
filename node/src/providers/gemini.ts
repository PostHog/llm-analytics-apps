import { GoogleGenAI as PostHogGoogleGenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { BaseProvider, Tool } from './base.js';

export class GeminiProvider extends BaseProvider {
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
    return 'Google Gemini';
  }

  resetConversation(): void {
    this.history = [];
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
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

    const requestParams = {
      model: 'gemini-2.5-flash',
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || 'user-hog',
      contents: this.history,
      config: this.config
    };

    const message = await this.client.models.generateContent(requestParams);
    this.debugApiCall("Google Gemini", requestParams, message);

    const displayParts: string[] = [];
    const modelParts: any[] = [];
    const toolResults: string[] = [];

    if (message.candidates) {
      for (const candidate of message.candidates) {
        if (candidate.content) {
          for (const part of candidate.content.parts) {
            if (part.functionCall) {
              const functionCall = part.functionCall;
              modelParts.push({ functionCall });
              
              if (functionCall.name === 'get_current_weather') {
                const location = functionCall.args?.location || 'unknown';
                const weatherResult = this.getWeather(location);
                const toolResultText = this.formatToolResult('get_weather', weatherResult);
                toolResults.push(toolResultText);
                displayParts.push(toolResultText);
              }
            } else if (part.text) {
              modelParts.push({ text: part.text });
              displayParts.push(part.text);
            }
          }
        }
      }
    }

    // Add model response to history
    if (modelParts.length > 0) {
      this.history.push({
        role: 'model',
        parts: modelParts
      });
    }
    
    for (const toolResult of toolResults) {
      this.history.push({
        role: 'model',
        parts: [{ text: `Tool result: ${toolResult}` }]
      });
    }

    return displayParts.length > 0 ? displayParts.join('\n\n') : (message.text || 'No response received');
  }
}