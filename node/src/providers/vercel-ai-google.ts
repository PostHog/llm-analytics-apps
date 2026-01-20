import { withTracing } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { generateText } from 'ai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { z } from 'zod';
import { BaseProvider, Message, Tool } from './base.js';
import { GEMINI_MODEL, GEMINI_IMAGE_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class VercelAIGoogleProvider extends BaseProvider {
  private googleClient: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.googleClient = createGoogleGenerativeAI({
      apiKey: process.env.GEMINI_API_KEY!
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
    return 'Vercel AI SDK (Google)';
  }

  async generateImage(prompt: string, model: string = GEMINI_IMAGE_MODEL): Promise<string> {
    try {
      // Gemini 2.5 Flash Image uses generateText with multimodal output
      const tracedModel = withTracing(this.googleClient(model), this.posthogClient, {
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogPrivacyMode: false,
        posthogProperties: {
          $ai_span_name: "vercel_ai_generate_image_google",
          ...this.getPostHogProperties(),
        },
      });

      const result = await generateText({
        model: tracedModel,
        prompt: prompt,
      });

      this.debugApiCall("Vercel AI SDK Image Generation (Google)", { model, prompt }, result);

      // Generated images are returned in result.files array
      if (result.files && result.files.length > 0) {
        for (const file of result.files) {
          if (file.mediaType?.startsWith('image/')) {
            // Convert Uint8Array to base64
            const b64 = Buffer.from(file.uint8Array).toString('base64');
            return `data:${file.mediaType};base64,${b64.substring(0, 100)}... (base64 image data, ${b64.length} chars total)`;
          }
        }
      }
      return "";
    } catch (error: any) {
      console.error('Error in Vercel AI Google image generation:', error);
      throw new Error(`Vercel AI Google Image Generation error: ${error.message}`);
    }
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
      const model = withTracing(this.googleClient(GEMINI_MODEL), this.posthogClient, {
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogPrivacyMode: false,
        posthogProperties: {
          $ai_span_name: "vercel_ai_generate_text_google",
          ...this.getPostHogProperties(),
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
          },
          tell_joke: {
            description: 'Tell a joke with a question-style setup and an answer punchline',
            inputSchema: z.object({
              setup: z.string().describe('The setup of the joke, usually in question form'),
              punchline: z.string().describe('The punchline or answer to the joke')
            }),
            execute: async ({ setup, punchline }: { setup: string; punchline: string }) => {
              return this.tellJoke(setup, punchline);
            }
          }
        }
      };

      const { text, toolResults } = await generateText(requestParams);
      this.debugApiCall("Vercel AI SDK (Google)", requestParams, { text, toolResults });

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
          } else if (result.toolName === 'tell_joke' && 'output' in result) {
            const toolResultText = this.formatToolResult('tell_joke', result.output as string);
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
      console.error('Error in Vercel AI Google chat:', error);
      throw new Error(`Vercel AI Google Provider error: ${error.message}`);
    }
  }
}
