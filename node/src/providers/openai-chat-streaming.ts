import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { StreamingProvider, Message, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, OPENAI_EMBEDDING_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class OpenAIChatStreamingProvider extends StreamingProvider {
  private client: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
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
      }
    ];
  }

  getName(): string {
    return 'OpenAI Chat Completions Streaming';
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

  async *chatStream(
    userInput: string,
    base64Image?: string
  ): AsyncGenerator<string, void, unknown> {
    let userContent: any;

    if (base64Image) {
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
      model: base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL,
      max_tokens: DEFAULT_MAX_TOKENS,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      posthogProperties: {
        $ai_span_name: "openai_chat_completions_streaming",
        ...this.getPostHogProperties(),
      },
      messages: this.messages,
      tools: this.tools,
      tool_choice: 'auto',
      stream: true,
      stream_options: {
        include_usage: true
      }
    };

    if (this.debugMode) {
      this.debugLog("OpenAI Chat Completions Streaming API Request", requestParams);
    }

    const stream = await this.client.chat.completions.create(requestParams);

    let accumulatedContent = '';
    const toolCalls: any[] = [];
    const toolCallsByIndex: Map<number, any> = new Map();

    for await (const chunk of stream) {
      // Handle text content
      if (chunk.choices?.[0]?.delta?.content) {
        const content = chunk.choices[0].delta.content;
        accumulatedContent += content;
        yield content;
      }

      // Handle tool calls
      if (chunk.choices?.[0]?.delta?.tool_calls) {
        for (const toolCallDelta of chunk.choices[0].delta.tool_calls) {
          const index = toolCallDelta.index;

          // Initialize or get existing tool call
          if (!toolCallsByIndex.has(index)) {
            toolCallsByIndex.set(index, {
              id: toolCallDelta.id || '',
              type: 'function',
              function: {
                name: toolCallDelta.function?.name || '',
                arguments: ''
              }
            });
          }

          const toolCall = toolCallsByIndex.get(index)!;

          // Update tool call information
          if (toolCallDelta.id) {
            toolCall.id = toolCallDelta.id;
          }
          if (toolCallDelta.function?.name) {
            toolCall.function.name = toolCallDelta.function.name;
          }
          if (toolCallDelta.function?.arguments) {
            toolCall.function.arguments += toolCallDelta.function.arguments;
          }
        }
      }

      // Check for finish reason to know when tool calls are complete
      if (chunk.choices?.[0]?.finish_reason === 'tool_calls') {
        // Convert map to array and execute tools
        const completedToolCalls = Array.from(toolCallsByIndex.values());
        
        for (const toolCall of completedToolCalls) {
          toolCalls.push(toolCall);
          
          if (toolCall.function.name === 'get_weather') {
            try {
              const args = JSON.parse(toolCall.function.arguments);
              const latitude = args.latitude || 0.0;
              const longitude = args.longitude || 0.0;
              const locationName = args.location_name;
              const weatherResult = await this.getWeather(latitude, longitude, locationName);
              const toolResultText = this.formatToolResult('get_weather', weatherResult);
              yield '\n\n' + toolResultText;
            } catch (e) {
              console.error('Error parsing tool arguments:', e);
            }
          }
        }
      }
    }

    // Save assistant message
    const assistantMessage: Message = {
      role: 'assistant',
      content: accumulatedContent || undefined
    };

    if (toolCalls.length > 0) {
      assistantMessage.tool_calls = toolCalls;
    }

    this.messages.push(assistantMessage);

    // Debug: Log the completed stream response
    if (this.debugMode) {
      this.debugLog("OpenAI Chat Completions Streaming API Response (completed)", {
        accumulatedContent: accumulatedContent,
        toolCalls: toolCalls
      });
    }

    // Add tool results to messages if any tools were called
    for (const toolCall of toolCalls) {
      if (toolCall.function.name === 'get_weather') {
        try {
          const args = JSON.parse(toolCall.function.arguments);
          const latitude = args.latitude || 0.0;
          const longitude = args.longitude || 0.0;
          const locationName = args.location_name;
          const weatherResult = await this.getWeather(latitude, longitude, locationName);

          const toolResultMessage: any = {
            role: 'tool',
            tool_call_id: toolCall.id,
            content: weatherResult
          };
          this.messages.push(toolResultMessage);
        } catch (e) {
          console.error('Error adding tool result:', e);
        }
      }
    }
  }

  // Non-streaming chat for compatibility
  async chat(userInput: string, base64Image?: string): Promise<string> {
    const chunks: string[] = [];
    for await (const chunk of this.chatStream(userInput, base64Image)) {
      chunks.push(chunk);
    }
    return chunks.join('');
  }
}