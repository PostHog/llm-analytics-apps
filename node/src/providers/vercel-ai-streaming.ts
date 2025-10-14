import { withTracing } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { streamText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { StreamingProvider, Message, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_FRIENDLY } from './constants.js';

export class VercelAIStreamingProvider extends StreamingProvider {
  private openaiClient: any;

  constructor(posthogClient: PostHog) {
    super(posthogClient);
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
    return 'Vercel AI SDK Streaming (OpenAI)';
  }

  async *chatStream(
    userInput: string,
    base64Image?: string
  ): AsyncGenerator<string, void, unknown> {
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

    // Use vision model for images, regular model otherwise
    const modelName = base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL;
    const model = withTracing(this.openaiClient(modelName), this.posthogClient, {
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      posthogPrivacyMode: false
    });

    try {
      const requestParams = {
        model: model,
        messages: this.messages as any,
        maxOutputTokens: DEFAULT_MAX_TOKENS,
        tools: {
          get_weather: {
            description: 'Get the current weather for a specific location',
            inputSchema: z.object({
              location: z.string().describe('The city or location name to get weather for')
            }),
            execute: async ({ location }: { location: string }) => {
              return this.getWeather(location);
            }
          }
        }
      };

      if (this.debugMode) {
        this.debugLog("Vercel AI SDK Streaming (OpenAI) API Request", requestParams);
      }

      const result = await streamText(requestParams);

      let accumulatedContent = '';
      const toolCalls: any[] = [];
      let currentToolCall: any = null;

      for await (const part of result.fullStream) {
        // Handle text delta events
        if (part.type === 'text-delta') {
          const delta = (part as any).text || '';
          accumulatedContent += delta;
          yield delta;
        }

        // Handle tool call start
        if (part.type === 'tool-call') {
          currentToolCall = {
            toolName: (part as any).toolName,
            args: (part as any).input || {}
          };
          toolCalls.push(currentToolCall);
        }

        // Handle tool result
        if (part.type === 'tool-result') {
          const toolResult = part as any;
          if (toolResult.toolName === 'get_weather') {
            // The tool was already executed via the execute function
            // Format and yield the result
            const weatherResult = toolResult.output as string;
            const toolResultText = this.formatToolResult('get_weather', weatherResult);
            yield '\n\n' + toolResultText;
          }
        }

        // Handle finish event for usage tracking
        if (part.type === 'finish') {
          // Usage information is available in part.usage if needed
          // but we're already tracking this via withTracing
        }
      }

      // Save assistant message with accumulated content
      if (accumulatedContent) {
        const assistantMessage: Message = {
          role: 'assistant',
          content: accumulatedContent
        };
        this.messages.push(assistantMessage);
      } else if (toolCalls.length > 0) {
        // If there was a tool call but no text content, save the tool result as assistant message
        let toolResultsText = '';
        for (const toolCall of toolCalls) {
          if (toolCall.toolName === 'get_weather') {
            const location = toolCall.args.location || 'unknown';
            const weatherResult = this.getWeather(location);
            toolResultsText += this.formatToolResult('get_weather', weatherResult);
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

      // Debug: Log the completed stream response
      if (this.debugMode) {
        this.debugLog("Vercel AI SDK Streaming (OpenAI) API Response (completed)", {
          accumulatedContent: accumulatedContent,
          toolCalls: toolCalls
        });
      }
    } catch (error: any) {
      console.error('Error in Vercel AI streaming chat:', error);
      throw new Error(`Vercel AI Streaming Provider error: ${error.message}`);
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