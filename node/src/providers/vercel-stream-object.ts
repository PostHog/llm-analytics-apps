import { withTracing } from '@posthog/ai';
import { PostHog } from 'posthog-node';
import { streamObject } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { StreamingProvider, Message, Tool } from './base.js';
import { OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_POSTHOG_DISTINCT_ID, SYSTEM_PROMPT_STRUCTURED } from './constants.js';

// Define schemas for different types of structured outputs
const weatherSchema = z.object({
  location: z.string().describe('The location for which weather is provided'),
  temperature: z.number().describe('Temperature in Celsius'),
  condition: z.string().describe('Weather condition description'),
  humidity: z.number().describe('Humidity percentage'),
  windSpeed: z.number().describe('Wind speed in km/h'),
  forecast: z.array(z.object({
    day: z.string().describe('Day of the week'),
    high: z.number().describe('High temperature'),
    low: z.number().describe('Low temperature'),
    condition: z.string().describe('Weather condition')
  })).describe('3-day weather forecast')
});

const userProfileSchema = z.object({
  name: z.string().describe('User\'s name'),
  interests: z.array(z.string()).describe('List of user interests'),
  preferences: z.object({
    communicationStyle: z.enum(['formal', 'casual', 'friendly']).describe('Preferred communication style'),
    topics: z.array(z.string()).describe('Preferred conversation topics')
  }).describe('User preferences'),
  demographics: z.object({
    ageRange: z.string().describe('Age range (e.g., 20-30)'),
    location: z.string().optional().describe('General location if mentioned')
  }).describe('Basic demographic information')
});

const taskPlanSchema = z.object({
  title: z.string().describe('Title of the task or project'),
  objective: z.string().describe('Main objective or goal'),
  steps: z.array(z.object({
    stepNumber: z.number().describe('Step number in sequence'),
    title: z.string().describe('Step title'),
    description: z.string().describe('Detailed description of the step'),
    estimatedTime: z.string().describe('Estimated time to complete'),
    dependencies: z.array(z.string()).describe('Dependencies on other steps')
  })).describe('List of steps to complete the task'),
  totalEstimatedTime: z.string().describe('Total estimated time for the entire task'),
  resources: z.array(z.string()).describe('Required resources or tools'),
  risks: z.array(z.string()).describe('Potential risks or challenges')
});

export class VercelStreamObjectProvider extends StreamingProvider {
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
        content: SYSTEM_PROMPT_STRUCTURED
      }
    ];
  }

  protected getToolDefinitions(): Tool[] {
    // Vercel AI SDK doesn't use this, but we need to implement it
    return [];
  }

  getName(): string {
    return 'Vercel AI SDK - streamObject (OpenAI)';
  }

  // Determine which schema to use based on user input
  private determineSchema(userInput: string): { schema: z.ZodSchema<any>, type: string } {
    const input = userInput.toLowerCase();
    
    if (input.includes('weather') || input.includes('temperature') || input.includes('forecast')) {
      return { schema: weatherSchema, type: 'weather' };
    } else if (input.includes('profile') || input.includes('about me') || input.includes('interests')) {
      return { schema: userProfileSchema, type: 'profile' };
    } else if (input.includes('plan') || input.includes('task') || input.includes('project') || input.includes('steps')) {
      return { schema: taskPlanSchema, type: 'plan' };
    }
    
    // Default to user profile for general queries
    return { schema: userProfileSchema, type: 'profile' };
  }

  async *chatStream(
    userInput: string,
    base64Image?: string
  ): AsyncGenerator<string, void, unknown> {
    let userContent: any;
    
    if (base64Image) {
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

    const { schema, type } = this.determineSchema(userInput);
    const modelName = base64Image ? OPENAI_VISION_MODEL : OPENAI_CHAT_MODEL;
    const model = withTracing(this.openaiClient(modelName), this.posthogClient, {
      posthogDistinctId: process.env.POSTHOG_DISTINCT_ID || DEFAULT_POSTHOG_DISTINCT_ID,
      posthogPrivacyMode: false
    });

    try {
      let prompt = userInput;
      if (type === 'weather') {
        prompt = `Provide detailed weather information for the location mentioned in: "${userInput}". If no specific location is mentioned, use Montreal, Canada as default.`;
      } else if (type === 'profile') {
        prompt = `Based on this user message: "${userInput}", create a user profile. If limited information is available, make reasonable assumptions about interests and preferences.`;
      } else if (type === 'plan') {
        prompt = `Create a detailed task plan based on: "${userInput}". Break it down into specific, actionable steps.`;
      }

      const requestParams = {
        model: model,
        messages: [
          ...this.messages.slice(0, -1), // All previous messages except the last user message
          { role: 'user', content: prompt }
        ] as any,
        schema: schema,
        maxOutputTokens: DEFAULT_MAX_TOKENS,
      };

      if (this.debugMode) {
        this.debugLog("Vercel AI SDK - streamObject (OpenAI) API Request", requestParams);
      }

      const result = await streamObject(requestParams);

      yield `🔄 Generating structured ${type} data...\n\n`;

      let previousFormatted = '';
      for await (const partialResult of result.partialObjectStream) {
        const formatted = this.formatStructuredData(partialResult, type);
        
        // Only yield the new content (difference from previous)
        if (formatted !== previousFormatted) {
          // Clear the previous line and write new content
          if (previousFormatted) {
            // Calculate lines to clear based on previous content
            const linesToClear = previousFormatted.split('\n').length;
            for (let i = 0; i < linesToClear; i++) {
              yield '\x1b[1A\x1b[2K'; // Move up one line and clear it
            }
          }
          yield formatted;
          previousFormatted = formatted;
        }
      }

      // Final result
      const finalObject = await result.object;
      const finalFormatted = this.formatStructuredData(finalObject, type);
      
      // Clear previous content and show final result
      if (previousFormatted) {
        const linesToClear = previousFormatted.split('\n').length;
        for (let i = 0; i < linesToClear; i++) {
          yield '\x1b[1A\x1b[2K'; // Move up one line and clear it
        }
      }
      
      yield `✅ Complete ${type} data:\n${finalFormatted}`;

      // Save assistant message with the structured data
      const assistantMessage: Message = {
        role: 'assistant',
        content: `Generated ${type} data: ${JSON.stringify(finalObject, null, 2)}`
      };
      this.messages.push(assistantMessage);

      // Debug: Log the completed stream response
      if (this.debugMode) {
        this.debugLog("Vercel AI SDK - streamObject (OpenAI) API Response (completed)", {
          type: type,
          finalObject: finalObject,
          finalFormatted: finalFormatted
        });
      }

    } catch (error: any) {
      console.error('Error in Vercel streamObject streaming:', error);
      throw new Error(`Vercel streamObject Streaming Provider error: ${error.message}`);
    }
  }

  private formatStructuredData(data: any, type: string): string {
    if (!data) return '';

    try {
      if (type === 'weather' && data) {
        let output = '';
        if (data.location) output += `📍 Location: ${data.location}\n`;
        if (data.temperature !== undefined) output += `🌡️  Temperature: ${data.temperature}°C\n`;
        if (data.condition) output += `☁️  Condition: ${data.condition}\n`;
        if (data.humidity !== undefined) output += `💧 Humidity: ${data.humidity}%\n`;
        if (data.windSpeed !== undefined) output += `💨 Wind Speed: ${data.windSpeed} km/h\n`;
        
        if (data.forecast && data.forecast.length > 0) {
          output += `\n📅 3-Day Forecast:\n`;
          data.forecast.forEach((day: any, index: number) => {
            if (day.day) output += `  ${day.day}: `;
            if (day.high !== undefined && day.low !== undefined) {
              output += `${day.high}°/${day.low}° `;
            }
            if (day.condition) output += `${day.condition}`;
            output += '\n';
          });
        }
        return output;
      }

      if (type === 'profile' && data) {
        let output = '';
        if (data.name) output += `👤 Name: ${data.name}\n`;
        if (data.interests && data.interests.length > 0) {
          output += `🎯 Interests: ${data.interests.join(', ')}\n`;
        }
        if (data.preferences) {
          output += `\n⚙️  Preferences:\n`;
          if (data.preferences.communicationStyle) {
            output += `  • Communication: ${data.preferences.communicationStyle}\n`;
          }
          if (data.preferences.topics && data.preferences.topics.length > 0) {
            output += `  • Topics: ${data.preferences.topics.join(', ')}\n`;
          }
        }
        if (data.demographics) {
          output += `\n📊 Demographics:\n`;
          if (data.demographics.ageRange) {
            output += `  • Age Range: ${data.demographics.ageRange}\n`;
          }
          if (data.demographics.location) {
            output += `  • Location: ${data.demographics.location}\n`;
          }
        }
        return output;
      }

      if (type === 'plan' && data) {
        let output = '';
        if (data.title) output += `📋 ${data.title}\n`;
        if (data.objective) output += `🎯 Objective: ${data.objective}\n`;
        if (data.totalEstimatedTime) output += `⏱️  Total Time: ${data.totalEstimatedTime}\n\n`;
        
        if (data.steps && data.steps.length > 0) {
          output += `📝 Steps:\n`;
          data.steps.forEach((step: any) => {
            if (step.stepNumber && step.title) {
              output += `  ${step.stepNumber}. ${step.title}\n`;
            }
            if (step.description) output += `     ${step.description}\n`;
            if (step.estimatedTime) output += `     ⏱️  ${step.estimatedTime}\n`;
            if (step.dependencies && step.dependencies.length > 0) {
              output += `     🔗 Depends on: ${step.dependencies.join(', ')}\n`;
            }
            output += '\n';
          });
        }

        if (data.resources && data.resources.length > 0) {
          output += `🛠️  Resources: ${data.resources.join(', ')}\n`;
        }
        if (data.risks && data.risks.length > 0) {
          output += `⚠️  Risks: ${data.risks.join(', ')}\n`;
        }
        return output;
      }

      // Fallback to JSON formatting
      return JSON.stringify(data, null, 2);
    } catch (error) {
      return JSON.stringify(data, null, 2);
    }
  }

  // Non-streaming version for compatibility
  async chat(userInput: string, base64Image?: string): Promise<string> {
    const chunks: string[] = [];
    for await (const chunk of this.chatStream(userInput, base64Image)) {
      chunks.push(chunk);
    }
    return chunks.join('');
  }
}
