import { OpenAI as PostHogOpenAI } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { BaseProvider } from './base.js';
import { DEFAULT_POSTHOG_DISTINCT_ID } from './constants.js';
import * as fs from 'fs';

export class OpenAITranscriptionProvider extends BaseProvider {
  private client: any;

  constructor(posthogClient: PostHog, aiSessionId: string | null = null) {
    super(posthogClient, aiSessionId);
    this.client = new PostHogOpenAI({
      apiKey: process.env.OPENAI_API_KEY!,
      posthog: posthogClient
    });
  }

  protected getToolDefinitions(): any[] {
    // Transcription doesn't use tools
    return [];
  }

  getName(): string {
    return 'OpenAI Transcriptions';
  }

  /**
   * Transcribe audio from a file path or buffer
   * @param audioPath Path to the audio file (supports mp3, mp4, mpeg, mpga, m4a, wav, webm)
   * @param model Model to use (default: whisper-1)
   * @param language Optional language code (e.g., 'en')
   * @param prompt Optional prompt to guide transcription
   * @returns Transcription text
   */
  async transcribe(
    audioPath: string,
    model: string = 'whisper-1',
    language?: string,
    prompt?: string
  ): Promise<string> {
    try {
      const audioFile = fs.createReadStream(audioPath);

      const transcriptionParams: any = {
        file: audioFile,
        model: model,
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogProperties: this.getPostHogProperties()
      };

      // Add optional parameters
      if (language) {
        transcriptionParams.language = language;
      }
      if (prompt) {
        transcriptionParams.prompt = prompt;
      }

      const transcription = await this.client.audio.transcriptions.create(transcriptionParams);

      this.debugApiCall("OpenAI Transcription", transcriptionParams, transcription);

      return transcription.text || 'No transcription generated';
    } catch (error: any) {
      console.error('Transcription error:', error);
      throw error;
    }
  }

  /**
   * Transcribe audio with verbose response format
   * @param audioPath Path to the audio file
   * @param model Model to use (default: whisper-1)
   * @param language Optional language code
   * @param prompt Optional prompt to guide transcription
   * @returns Verbose transcription with segments, language, duration
   */
  async transcribeVerbose(
    audioPath: string,
    model: string = 'whisper-1',
    language?: string,
    prompt?: string
  ): Promise<any> {
    try {
      const audioFile = fs.createReadStream(audioPath);

      const transcriptionParams: any = {
        file: audioFile,
        model: model,
        response_format: 'verbose_json',
        posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
        posthogProperties: this.getPostHogProperties()
      };

      // Add optional parameters
      if (language) {
        transcriptionParams.language = language;
      }
      if (prompt) {
        transcriptionParams.prompt = prompt;
      }

      const transcription = await this.client.audio.transcriptions.create(transcriptionParams);

      this.debugApiCall("OpenAI Transcription (Verbose)", transcriptionParams, transcription);

      return transcription;
    } catch (error: any) {
      console.error('Transcription error:', error);
      throw error;
    }
  }

  // Override chat method (not used for transcriptions)
  async chat(userInput: string): Promise<string> {
    return 'This provider is for transcriptions only. Use transcribe() method instead.';
  }
}
