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
            latitude: {
              type: 'number',
              description: 'The latitude of the location (e.g., 37.7749 for San Francisco)'
            },
            longitude: {
              type: 'number',
              description: 'The longitude of the location (e.g., -122.4194 for San Francisco)'
            },
            location_name: {
              type: 'string',
              description: 'A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')'
            }
          },
          required: ['latitude', 'longitude', 'location_name']
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
      posthogProperties: {
        $ai_span_name: "openai_responses",
      },
      input: this.messages,
      instructions: SYSTEM_PROMPT_FRIENDLY,
      tools: this.tools
    };

    const message = await this.client.responses.create(requestParams);
    this.debugApiCall("OpenAI Responses", requestParams, message);

    const displayParts: string[] = [];
    const assistantContentItems: any[] = [];
    let toolCallForHistory: any = null;

    if (message.output) {
      for (const outputItem of message.output) {
        // Handle message content (text)
        if (outputItem.content) {
          for (const contentItem of outputItem.content) {
            if (contentItem.text) {
              displayParts.push(contentItem.text);
              // Add to conversation history as output_text
              assistantContentItems.push({
                type: 'output_text',
                text: contentItem.text
              });
            }
          }
        }

        // Handle tool calls (separate output items in Responses API)
        if (outputItem.name === 'get_weather') {
          // Get the tool call details from the response
          const callId = outputItem.call_id || `call_${outputItem.name}`;
          const toolArguments = outputItem.arguments || '{}';

          // Parse arguments to execute the tool
          let args: any = {};
          try {
            args = JSON.parse(toolArguments);
          } catch (e) {
            args = {};
          }

          const latitude = args.latitude || 0.0;
          const longitude = args.longitude || 0.0;
          const locationName = args.location_name;
          const weatherResult = await this.getWeather(latitude, longitude, locationName);
          const toolResultText = this.formatToolResult('get_weather', weatherResult);
          displayParts.push(toolResultText);

          // Store tool call info to add to conversation history
          toolCallForHistory = {
            id: callId,
            name: outputItem.name,
            result: weatherResult
          };
        }
      }
    }

    // Add messages to conversation history
    // For client-side history management, add tool results as assistant messages with output_text
    if (toolCallForHistory) {
      assistantContentItems.push({
        type: 'output_text',
        text: toolCallForHistory.result
      });
    }

    if (assistantContentItems.length > 0) {
      const assistantMessage: Message = {
        role: 'assistant',
        content: assistantContentItems
      };
      this.messages.push(assistantMessage);
    }

    return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
  }
}