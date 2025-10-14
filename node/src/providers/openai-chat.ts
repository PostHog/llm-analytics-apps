import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { BaseProvider, Message, Tool } from './base.js';
import {
  OPENAI_CHAT_MODEL,
  OPENAI_VISION_MODEL,
  OPENAI_EMBEDDING_MODEL,
  DEFAULT_MAX_TOKENS,
  DEFAULT_POSTHOG_DISTINCT_ID,
  SYSTEM_PROMPT_FRIENDLY,
} from './constants.js';

export class OpenAIChatProvider extends BaseProvider {
  private client: any;

  constructor(posthogClient: PostHog) {
    super(posthogClient);
    this.client = new PostHogOpenAI({
      apiKey: process.env.OPENAI_API_KEY!,
      posthog: posthogClient
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
    return [
      {
        type: 'function',
        function: {
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
      }
    ];
  }

  getName(): string {
    return 'OpenAI Chat Completions';
  }

  async embed(text: string, model: string = OPENAI_EMBEDDING_MODEL): Promise<number[]> {
    const response = await this.client.embeddings.create({
      model: model,
      input: text
    });

    if (response.data && response.data.length > 0) {
      return response.data[0].embedding;
    }
    return [];
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    let userContent: any;
    
    if (base64Image) {
      // For image input, create content array with text and image
      userContent = [
        {
          type: 'text',
          text: userInput
        },
        {
          type: 'image_url',
          image_url: {
            url: `data:image/png;base64,${base64Image}`
          }
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

    const requestParams = {
      model: base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL,  // Use vision model for images
      max_tokens: DEFAULT_MAX_TOKENS,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      messages: this.messages,
      tools: this.tools,
      tool_choice: 'auto'
    };

    const response = await this.client.chat.completions.create(requestParams);
    this.debugApiCall("OpenAI Chat Completions", requestParams, response);

    const displayParts: string[] = [];
    let assistantContent = '';

    const choice = response.choices[0];
    const message = choice.message;

    if (message.content) {
      assistantContent = message.content;
      displayParts.push(message.content);
    }

    if (message.tool_calls) {
      for (const toolCall of message.tool_calls) {
        if (toolCall.function.name === 'get_weather') {
          try {
            const args = JSON.parse(toolCall.function.arguments);
            const location = args.location || 'unknown';
            const weatherResult = this.getWeather(location);
            const toolResultText = this.formatToolResult('get_weather', weatherResult);
            displayParts.push(toolResultText);

            this.messages.push({
              role: 'assistant',
              content: assistantContent,
              tool_calls: [
                {
                  id: toolCall.id,
                  type: 'function',
                  function: {
                    name: toolCall.function.name,
                    arguments: toolCall.function.arguments
                  }
                }
              ]
            });

            this.messages.push({
              role: 'tool',
              tool_call_id: toolCall.id,
              content: weatherResult
            } as any);

          } catch (e) {
            displayParts.push('❌ Error parsing tool arguments');
          }
        }
      }
    } else {
      if (assistantContent) {
        const assistantMessage: Message = {
          role: 'assistant',
          content: assistantContent
        };
        this.messages.push(assistantMessage);
      }
    }

    return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
  }
}