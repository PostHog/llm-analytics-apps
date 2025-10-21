import { LangChainCallbackHandler } from '@posthog/ai';
import { ChatOpenAI } from '@langchain/openai';
import { ChatPromptTemplate } from '@langchain/core/prompts';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { HumanMessage, SystemMessage, ToolMessage } from '@langchain/core/messages';
import { PostHog } from 'posthog-node';
import { BaseProvider, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, SYSTEM_PROMPT_ASSISTANT } from './constants.js';

export class LangChainProvider extends BaseProvider {
  private callbackHandler: any;
  private langchainMessages: any[] = [];
  private langchainTools: any[] = [];
  private toolMap: Map<string, any> = new Map();

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.callbackHandler = new LangChainCallbackHandler({
      client: posthogClient,
      properties: {
        $ai_span_name: "langchain_chat",
        ...this.getPostHogProperties(),
      },
    });

    this.langchainMessages = [
      new SystemMessage(SYSTEM_PROMPT_ASSISTANT)
    ];

    this.setupChain();
  }

  protected getToolDefinitions(): Tool[] {
    // LangChain doesn't use this, but we need to implement it
    return [];
  }

  private setupChain(): void {
    const getWeatherTool = new DynamicStructuredTool({
      name: 'get_weather',
      description: 'Get the current weather for a specific location',
      schema: z.object({
        latitude: z.number().describe('The latitude of the location (e.g., 37.7749 for San Francisco)'),
        longitude: z.number().describe('The longitude of the location (e.g., -122.4194 for San Francisco)'),
        location_name: z.string().describe('A human-readable name for the location (e.g., \'San Francisco, CA\' or \'Dublin, Ireland\')'),
      }),
      func: async (input: { latitude: number; longitude: number; location_name: string }) => {
        return this.getWeather(input.latitude, input.longitude, input.location_name);
      }
    } as any) as any;

    this.langchainTools = [getWeatherTool];
    this.toolMap.set('get_weather', getWeatherTool);

    const prompt = ChatPromptTemplate.fromMessages([
      ['system', SYSTEM_PROMPT_ASSISTANT],
      ['user', '{input}']
    ]);

    const model = new ChatOpenAI({ openAIApiKey: process.env.OPENAI_API_KEY, temperature: 0 });
    prompt.pipe(model.bindTools(this.langchainTools));
  }

  getName(): string {
    return 'LangChain (OpenAI)';
  }

  getDescription(): string {
    return '💡 You can ask me about the weather!';
  }

  resetConversation(): void {
    this.langchainMessages = [
      new SystemMessage(SYSTEM_PROMPT_ASSISTANT)
    ];
    this.messages = [];
  }

  async chat(userInput: string, base64Image?: string): Promise<string> {
    let userMessage: any;
    
    if (base64Image) {
      // Create a message with image content
      userMessage = new HumanMessage({
        content: [
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
        ]
      });
    } else {
      userMessage = new HumanMessage(userInput);
    }
    
    this.langchainMessages.push(userMessage);

    const model = new ChatOpenAI({
      openAIApiKey: process.env.OPENAI_API_KEY,
      temperature: 0,
      modelName: base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL
    });
    const modelWithTools = model.bindTools(this.langchainTools);

    const requestParams = {
      messages: this.langchainMessages,
      callbacks: [this.callbackHandler]
    };

    const response = await modelWithTools.invoke(
      this.langchainMessages,
      { callbacks: [this.callbackHandler] }
    );
    this.debugApiCall("LangChain (OpenAI)", requestParams, response);

    const displayParts: string[] = [];

    if (response.content) {
      displayParts.push(response.content as string);
    }

    if (response.tool_calls && response.tool_calls.length > 0) {
      const toolMessages: any[] = [];
      for (const toolCall of response.tool_calls) {
        const toolName = toolCall.name;
        const toolArgs = toolCall.args;

        if (this.toolMap.has(toolName)) {
          const toolResult = await this.toolMap.get(toolName)!.invoke(toolArgs);
          const toolResultText = this.formatToolResult('get_weather', toolResult);
          displayParts.push(toolResultText);

          toolMessages.push(
            new ToolMessage({
              content: String(toolResult),
              tool_call_id: toolCall.id!,
            })
          );
        }
      }

      this.langchainMessages.push(response);
      this.langchainMessages.push(...toolMessages);
    } else {
      this.langchainMessages.push(response);
    }

    return displayParts.length > 0 ? displayParts.join('\n\n') : 'No response received';
  }
}