import { GoogleGenAI as PostHogGoogleGenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { BaseProvider, Tool } from './base.js';
import { GEMINI_IMAGE_MODEL, DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';

export class GeminiImageProvider extends BaseProvider {
  private client: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.client = new PostHogGoogleGenAI({
      apiKey: process.env.GEMINI_API_KEY!,
      posthog: posthogClient
    });
  }

  protected getToolDefinitions(): Tool[] {
    return [];
  }

  getName(): string {
    return 'Google Gemini (Image Generation)';
  }

  private logTokenUsageByModality(response: any): void {
    if (!this.debugMode) return;

    try {
      const usageMetadata = response?.usageMetadata;
      if (!usageMetadata) {
        console.log("\n📊 Token Usage: No modality breakdown available\n");
        return;
      }

      console.log("\n" + "─".repeat(60));
      console.log("📊 TOKEN USAGE BY MODALITY");
      console.log("─".repeat(60));

      // Input tokens breakdown
      const promptDetails = usageMetadata.promptTokensDetails || [];
      console.log("\n  INPUT TOKENS:");
      if (promptDetails.length > 0) {
        for (const detail of promptDetails) {
          console.log(`    ${detail.modality}: ${detail.tokenCount} tokens`);
        }
      } else {
        console.log(`    Total: ${usageMetadata.promptTokenCount || 0} tokens`);
      }

      // Output tokens breakdown
      const candidatesDetails = usageMetadata.candidatesTokensDetails || [];
      console.log("\n  OUTPUT TOKENS:");
      if (candidatesDetails.length > 0) {
        for (const detail of candidatesDetails) {
          console.log(`    ${detail.modality}: ${detail.tokenCount} tokens`);
        }
      } else {
        console.log(`    Total: ${usageMetadata.candidatesTokenCount || 0} tokens`);
      }

      console.log("\n  TOTAL: " + (usageMetadata.totalTokenCount || 0) + " tokens");
      console.log("─".repeat(60) + "\n");
    } catch (e) {
      // Silently ignore errors in debug logging
    }
  }

  async generateImage(prompt: string, model: string = GEMINI_IMAGE_MODEL): Promise<string> {
    try {
      const requestParams = {
        model: model,
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogProperties: {
          $ai_span_name: "gemini_generate_image",
          ...this.getPostHogProperties(),
        },
        contents: prompt
      };

      const response = await this.client.models.generateContent(requestParams);
      this.debugApiCall("Google Gemini Image Generation", requestParams, response);
      this.logTokenUsageByModality(response);

      // Check for images in the response candidates
      if (response.candidates) {
        for (const candidate of response.candidates) {
          if (candidate.content?.parts) {
            for (const part of candidate.content.parts) {
              // Check for inline image data
              if (part.inlineData?.data && part.inlineData?.mimeType?.startsWith('image/')) {
                const b64 = part.inlineData.data;
                return `data:${part.inlineData.mimeType};base64,${b64.substring(0, 100)}... (base64 image data, ${b64.length} chars total)`;
              }
            }
          }
        }
      }

      return "";
    } catch (error: any) {
      console.error('Error in Gemini image generation:', error);
      throw new Error(`Gemini Image Generation error: ${error.message}`);
    }
  }

  async chat(): Promise<string> {
    throw new Error('This provider is for image generation only. Use generateImage() instead.');
  }
}
