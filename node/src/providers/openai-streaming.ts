import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { StreamingProvider, Message, Tool } from './base.js';

export class OpenAIStreamingProvider extends StreamingProvider {
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
        name: 'get_weather',
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
    return 'OpenAI Responses Streaming';
  }

  async embed(text: string, model: string = 'text-embedding-3-small'): Promise<number[]> {
    const response = await this.client.embeddings.create({
      model: model,
      input: text,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || 'user-hog'
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

    const stream = await this.client.responses.create({
      model: base64Image ? 'gpt-4o' : 'gpt-4o-mini',  // Use vision model for images
      max_output_tokens: 200,
      temperature: 0.7,
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || 'user-hog',
      input: this.messages,
      instructions: 'You are a friendly AI that just makes conversation. You have access to a weather tool if the user asks about weather.',
      tools: this.tools,
      stream: true
    });

    let accumulatedContent = '';
    const finalOutput: any[] = [];
    const toolCalls: any[] = [];

    for await (const chunk of stream) {
      // Handle different streaming event types
      if (chunk.type === 'response.output_text.delta') {
        // Text delta streaming - this is the main text streaming event
        if (chunk.delta) {
          accumulatedContent += chunk.delta;
          yield chunk.delta;
        }
      } else if (chunk.type === 'response.output_item.added') {
        // Track when a function call starts
        if (chunk.item && chunk.item.type === 'function_call') {
          // Store the function name for later use
          if (!toolCalls[chunk.output_index]) {
            toolCalls[chunk.output_index] = {
              name: chunk.item.name || 'get_weather',
              arguments: ''
            };
          }
        }
      } else if (chunk.type === 'response.function_call_arguments.done') {
        // Function call arguments completed
        if (chunk.arguments && chunk.output_index !== undefined) {
          // Get the function info we stored earlier
          const toolCall = toolCalls[chunk.output_index];
          if (toolCall && toolCall.name === 'get_weather') {
            let args: any = {};
            try {
              args = JSON.parse(chunk.arguments);
            } catch (e) {
              args = {};
            }
            
            const location = args.location || 'unknown';
            const weatherResult = this.getWeather(location);
            const toolResultText = this.formatToolResult('get_weather', weatherResult);
            yield '\n\n' + toolResultText;
            
            // Update the arguments
            toolCall.arguments = chunk.arguments;
          }
        }
      } else if (chunk.type === 'response.completed' && chunk.response) {
        // Response completed event - only handle content that wasn't already streamed
        if (chunk.response.output && chunk.response.output.length > 0) {
          for (const outputItem of chunk.response.output) {
            // Check if this is a content message that wasn't already streamed
            if (outputItem.content && Array.isArray(outputItem.content)) {
              // Only add content if we didn't stream it already
              for (const contentItem of outputItem.content) {
                if (contentItem.text && !accumulatedContent.includes(contentItem.text)) {
                  accumulatedContent += contentItem.text;
                  yield contentItem.text;
                }
              }
            }
            
            // Tool calls are already handled in response.function_call_arguments.done
            // So we don't need to handle them here
          }
        }
      }
    }

    // Save assistant message with accumulated content or tool results
    if (accumulatedContent) {
      const assistantMessage: Message = {
        role: 'assistant',
        content: accumulatedContent
      };
      this.messages.push(assistantMessage);
    } else if (toolCalls.length > 0 && toolCalls.some(tc => tc.arguments)) {
      // If there was a tool call but no text content, save the tool result as assistant message
      let toolResultsText = '';
      for (const toolCall of toolCalls) {
        if (toolCall.arguments && toolCall.name === 'get_weather') {
          let args: any = {};
          try {
            args = JSON.parse(toolCall.arguments);
          } catch (e) {
            args = {};
          }
          const location = args.location || 'unknown';
          const weatherResult = this.getWeather(location);
          toolResultsText += weatherResult;
        }
      }
      
      if (toolResultsText) {
        const assistantMessage: Message = {
          role: 'assistant',
          content: toolResultsText
        };
        this.messages.push(assistantMessage);
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