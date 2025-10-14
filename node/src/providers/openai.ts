import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { BaseProvider, Message, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, OPENAI_EMBEDDING_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class OpenAIProvider extends BaseProvider {
  private client: any;

  constructor(posthogClient: PostHog) {
    super(posthogClient);
    this.client = new PostHogOpenAI({
      apiKey: process.env.OPENAI_API_KEY!,
      posthog: posthogClient
    });
  }

  protected getToolDefinitions(): Tool[] {
    return [
      {
        type: 'function',
        name: 'get_weather',
        description: 'Get the current weather for a specific location',
        parameters: {
          type: 'object',
          properties: {
            location: {
              type: 'string',
              description: 'The city or location name to get weather for'
            }
          },
          required: ['location']
        }
      }
    ];
  }

  getName(): string {
    return 'OpenAI Responses';
  }

  async embed(text: string, model: string = OPENAI_EMBEDDING_MODEL): Promise<number[]> {
    const response = await this.client.embeddings.create({
      model: model,
      input: text,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID
    });

    if (response.data && response.data.length > 0) {
      return response.data[0].embedding;
    }
    return [];
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    let userMessage: Message;
    
    if (base64Image) {
      // For image input, create content array with text and image
      userMessage = {
        role: 'user',
        content: [
          {
            type: 'input_text',
            text: userInput
          },
          {
            type: 'input_image',
            image_url: `data:image/png;base64,${base64Image}`
          }
        ] as any
      };
    } else {
      userMessage = {
        role: 'user',
        content: userInput
      };
    }
    
    this.messages.push(userMessage);

    const requestParams = {
      model: base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL,
      max_output_tokens: DEFAULT_MAX_TOKENS,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      input: this.messages,
      instructions: SYSTEM_PROMPT_FRIENDLY,
      tools: this.tools
    };

    const message = await this.client.responses.create(requestParams);
    this.debugApiCall("OpenAI Responses", requestParams, message);

    const displayParts: string[] = [];
    let assistantContent = '';

    if (message.output) {
      for (const outputItem of message.output) {
        if (outputItem.content) {
          for (const contentItem of outputItem.content) {
            if (contentItem.text) {
              assistantContent += contentItem.text;
              displayParts.push(contentItem.text);
            }
          }
        }

        if (outputItem.name === 'get_weather') {
          let args: any = {};
          if (outputItem.arguments) {
            try {
              args = JSON.parse(outputItem.arguments);
            } catch (e) {
              args = {};
            }
          }

          const location = args.location || 'unknown';
          const weatherResult = this.getWeather(location);
          const toolResultText = this.formatToolResult('get_weather', weatherResult);
          displayParts.push(toolResultText);
        }
      }
    }

    if (assistantContent) {
      const assistantMessage: Message = {
        role: 'assistant',
        content: assistantContent
      };
      this.messages.push(assistantMessage);
    }

    return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
  }
}