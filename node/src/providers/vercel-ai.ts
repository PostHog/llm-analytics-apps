import { withTracing } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { generateText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { BaseProvider, Message, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class VercelAIProvider extends BaseProvider {
  private openaiClient: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.openaiClient = createOpenAI({
      apiKey: process.env.OPENAI_API_KEY!
    });
    this.messages = this.getInitialMessages();
  }

  protected getInitialMessages(): Message[] {
    return [
      {
        role: 'system',
        content: SYSTEM_PROMPT_FRIENDLY
      }
    ];
  }

  protected getToolDefinitions(): Tool[] {
    // Vercel AI SDK doesn't use this, but we need to implement it
    return [];
  }

  getName(): string {
    return 'Vercel AI SDK (OpenAI)';
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    let userContent: any;
    
    if (base64Image) {
      // For image input, create content array with text and image
      userContent = [
        { type: 'text', text: userInput },
        { 
          type: 'image', 
          image: `data:image/png;base64,${base64Image}`
        }
      ];
    } else {
      userContent = userInput;
    }
    
    const userMessage: Message = {
      role: 'user',
      content: userContent
    };
    this.messages.push(userMessage);

    const displayParts: string[] = [];

    try {
      // Use vision model for images, regular model otherwise
      const modelName = base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL;
      const model = withTracing(this.openaiClient(modelName), this.posthogClient, {
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogPrivacyMode: false,
        posthogProperties: {
          $ai_span_name: "vercel_ai_generate_text",
        },
      });

      const requestParams = {
        model: model,
        messages: this.messages as any,
        maxOutputTokens: DEFAULT_MAX_TOKENS,
        tools: {
          get_weather: {
            description: 'Get the current weather for a specific location',
            inputSchema: z.object({
              latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
              longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
              location_name: z.string().describe('A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')')
            }),
            execute: async ({ latitude, longitude, location_name }: { latitude: number; longitude: number; location_name: string }) => {
              return this.getWeather(latitude, longitude, location_name);
            }
          }
        }
      };

      const { text, toolResults } = await generateText(requestParams);
      this.debugApiCall("Vercel AI SDK (OpenAI)", requestParams, { text, toolResults });

      if (text) {
        displayParts.push(text);
        const assistantMessage: Message = {
          role: 'assistant',
          content: text
        };
        this.messages.push(assistantMessage);
      }

      if (toolResults && toolResults.length > 0) {
        for (const result of toolResults) {
          if (result.toolName === 'get_weather' && 'output' in result) {
            const toolResultText = this.formatToolResult('get_weather', result.output as string);
            displayParts.push(toolResultText);
            
            // Add tool result to message history
            const toolMessage: Message = {
              role: 'assistant',
              content: toolResultText
            };
            this.messages.push(toolMessage);
          }
        }
      }

      return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
    } catch (error: any) {
      console.error('Error in Vercel AI chat:', error);
      throw new Error(`Vercel AI Provider error: ${error.message}`);
    }
  }
}