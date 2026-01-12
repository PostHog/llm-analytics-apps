#!/usr/bin/env node
/**
 * Test script to reproduce file parts error with withTracing + ToolLoopAgent
 *
 * Issue: "Cannot convert undefined or null to object" when using file parts
 * with Vercel AI SDK v6 ToolLoopAgent and PostHog withTracing
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { PostHog } from 'posthog-node';
import { withTracing } from '@posthog/ai';
import { ToolLoopAgent } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { z } from 'zod';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '..', '..', '.env') });
if (!process.env.POSTHOG_API_KEY) {
  dotenv.config({ path: path.join(__dirname, '..', '.env') });
}

const posthog = new PostHog(
  process.env.POSTHOG_API_KEY!,
  {
    host: process.env.POSTHOG_HOST || 'https://app.posthog.com',
    flushAt: 1,
    flushInterval: 0
  }
);

posthog.debug(true);
console.log(`\n📊 PostHog Config: host=${process.env.POSTHOG_HOST}, key=${process.env.POSTHOG_API_KEY?.substring(0, 10)}...`);

const googleClient = createGoogleGenerativeAI({
  apiKey: process.env.GEMINI_API_KEY!
});

// Test image - 1x1 red pixel PNG
const testBase64Image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==';

// Simple tool for testing
const weatherTool = {
  description: 'Get the current weather for a location',
  parameters: z.object({
    location: z.string().describe('The city name'),
  }),
  execute: async ({ location }: { location: string }) => {
    return `The weather in ${location} is sunny, 22°C`;
  },
};

async function testAgentWithFileParts() {
  console.log('\n🧪 Testing ToolLoopAgent with file parts and withTracing\n');
  console.log('='.repeat(60));

  try {
    const providerModel = googleClient('gemini-2.5-flash');

    const model = withTracing(providerModel, posthog, {
      posthogDistinctId: 'test-agent-file-parts-user',
      posthogPrivacyMode: false,
      posthogProperties: {
        $ai_span_name: 'agent_file_parts_test',
      },
    });

    // Create the agent
    const agent = new ToolLoopAgent({
      model,
      tools: {
        getWeather: weatherTool,
      },
      maxSteps: 5,
    });

    // Test with file content
    const messages = [
      {
        role: 'user' as const,
        content: [
          { type: 'text' as const, text: 'What do you see in this image? Also, what is the weather like in London?' },
          { type: 'file' as const, data: testBase64Image, mediaType: 'image/png' },
        ],
      },
    ];

    console.log('Running agent with file parts...\n');

    // Run the agent using generate method
    const result = await agent.generate({ messages });

    console.log('\n✅ SUCCESS');
    console.log('Agent response:', result.text?.substring(0, 200));

  } catch (error: any) {
    console.log('\n❌ FAILED');
    console.log(`Error: ${error.message}`);
    if (error.stack) {
      console.log(`\nStack trace:`);
      console.log(error.stack);
    }
  }
}

async function testAgentWithFilePartsStreaming() {
  console.log('\n🧪 Testing ToolLoopAgent with file parts and streaming\n');
  console.log('='.repeat(60));

  try {
    const providerModel = googleClient('gemini-2.5-flash');

    const model = withTracing(providerModel, posthog, {
      posthogDistinctId: 'test-agent-file-parts-streaming-user',
      posthogPrivacyMode: false,
      posthogProperties: {
        $ai_span_name: 'agent_file_parts_streaming_test',
      },
    });

    // Create the agent
    const agent = new ToolLoopAgent({
      model,
      tools: {
        getWeather: weatherTool,
      },
      maxSteps: 5,
    });

    // Test with file content
    const messages = [
      {
        role: 'user' as const,
        content: [
          { type: 'text' as const, text: 'What do you see in this image? Also, what is the weather like in Paris?' },
          { type: 'file' as const, data: testBase64Image, mediaType: 'image/png' },
        ],
      },
    ];

    console.log('Running agent with file parts (streaming)...\n');

    // Run the agent with streaming
    const result = await agent.stream({ messages });

    let fullText = '';
    for await (const chunk of result.textStream) {
      fullText += chunk;
      process.stdout.write(chunk);
    }

    console.log('\n\n✅ SUCCESS');
    console.log('Full response length:', fullText.length);

  } catch (error: any) {
    console.log('\n❌ FAILED');
    console.log(`Error: ${error.message}`);
    if (error.stack) {
      console.log(`\nStack trace:`);
      console.log(error.stack);
    }
  }
}

async function main() {
  console.log('\n🔬 Agent + File Parts Error Reproduction Test');
  console.log('Testing ToolLoopAgent with file parts and withTracing\n');

  const args = process.argv.slice(2);

  if (args.includes('--stream')) {
    await testAgentWithFilePartsStreaming();
  } else {
    await testAgentWithFileParts();
  }

  console.log('\nShutting down PostHog...');
  await posthog.shutdown();
  console.log('Done.');
}

main().catch(async (error) => {
  console.error('Fatal error:', error);
  await posthog.shutdown();
  process.exit(1);
});
