import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { BaseProvider, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';

export class OpenAIImageProvider extends BaseProvider {
  private client: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.client = new PostHogOpenAI({
      apiKey: process.env.OPENAI_API_KEY!,
      posthog: posthogClient
    });
  }

  protected getToolDefinitions(): Tool[] {
    return [];
  }

  getName(): string {
    return 'OpenAI Responses (Image Generation)';
  }

  async generateImage(prompt: string, model: string = OPENAI_CHAT_MODEL): Promise<string> {
    try {
      const requestParams = {
        model: model,
        input: prompt,
        tools: [{ type: 'image_generation' }],
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogProperties: this.getPostHogProperties()
      };

      const response = await this.client.responses.create(requestParams);
      this.debugApiCall("OpenAI Responses Image Generation", requestParams, response);

      // Extract image data from output array
      const imageData = response.output
        ?.filter((output: any) => output.type === 'image_generation_call')
        .map((output: any) => output.result);

      if (imageData && imageData.length > 0) {
        const imageBase64 = imageData[0];
        return `data:image/png;base64,${imageBase64.substring(0, 100)}... (base64 image data, ${imageBase64.length} chars total)`;
      }
      return "";
    } catch (error: any) {
      console.error('Error in OpenAI image generation:', error);
      throw new Error(`OpenAI Image Generation error: ${error.message}`);
    }
  }

  async chat(): Promise<string> {
    throw new Error('This provider is for image generation only. Use generateImage() instead.');
  }
}
