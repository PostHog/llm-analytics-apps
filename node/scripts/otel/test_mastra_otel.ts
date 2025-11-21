#!/usr/bin/env ts-node
/**
 * Test: Mastra OTEL Integration - Multi-turn conversation with tools
 *
 * Tests Mastra's OpenTelemetry instrumentation with PostHog ingestion.
 * Similar to the Python OTEL v2 tests but using Mastra framework.
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { Mastra, createTool } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { OtelExporter } from '@mastra/otel-exporter';
import { z } from 'zod';
import { trace } from '@opentelemetry/api';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables
dotenv.config({ path: path.join(__dirname, '..', '..', '..', '.env') });

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const POSTHOG_API_KEY = process.env.POSTHOG_API_KEY || 'phc_test';
const POSTHOG_PROJECT_ID = process.env.POSTHOG_PROJECT_ID || '1';
const POSTHOG_HOST = process.env.POSTHOG_HOST || 'http://localhost:8000';

console.log('\n' + '='.repeat(80));
console.log('TEST: Mastra OTEL - Multi-turn Conversation with Tools');
console.log('='.repeat(80));

if (!OPENAI_API_KEY) {
  console.log('❌ OPENAI_API_KEY not set');
  process.exit(1);
}

// Configure Mastra with OtelExporter pointing to PostHog OTEL endpoint
const tracesEndpoint = `${POSTHOG_HOST}/api/projects/${POSTHOG_PROJECT_ID}/ai/otel/v1/traces`;

const mastra = new Mastra({
  observability: {
    configs: {
      default: {
        serviceName: 'mastra-otel-test',
        exporters: [
          new OtelExporter({
            provider: {
              custom: {
                endpoint: tracesEndpoint,
                protocol: 'http/protobuf',
                headers: {
                  'Authorization': `Bearer ${POSTHOG_API_KEY}`,
                },
              },
            },
            timeout: 60000,
            logLevel: 'info',
            resourceAttributes: {
              'service.name': 'mastra-otel-test',
              'user.id': 'mastra-test-user',
            },
          }),
        ],
      },
    },
  },
});

// Define tools
const getWeatherTool = createTool({
  name: 'get_weather',
  description: 'Get weather for a location',
  inputSchema: z.object({
    location: z.string().describe('City name'),
  }),
  execute: async ({ context }) => {
    console.log(`[Tool] Getting weather for ${context.location}`);
    return { weather: 'Sunny', temperature: '18°C' };
  },
});

const tellJokeTool = createTool({
  name: 'tell_joke',
  description: 'Tell a joke',
  inputSchema: z.object({
    topic: z.string().describe('Joke topic'),
  }),
  execute: async ({ context }) => {
    console.log(`[Tool] Telling joke about ${context.topic}`);
    return { joke: 'Why do programmers prefer dark mode? Because light attracts bugs!' };
  },
});

// Create agent with tools
const agent = new Agent({
  name: 'test-agent',
  instructions: 'You are a helpful assistant with access to weather and jokes.',
  model: 'openai/gpt-4o-mini',
  tools: {
    get_weather: getWeatherTool,
    tell_joke: tellJokeTool,
  },
});

async function runConversation() {
  console.log('\n🗣️  CONVERSATION:');
  console.log('-'.repeat(80));

  try {
    // Turn 1: Greeting
    console.log('\n[1] User: Hi there!');
    let result = await agent.generate('Hi there!', {
      maxSteps: 5,
    });
    console.log(`[1] Assistant: ${result.text}`);

    // Turn 2: Weather tool call
    console.log('\n[2] User: What\'s the weather in Paris?');
    result = await agent.generate('What\'s the weather in Paris?', {
      maxSteps: 5,
    });
    console.log(`[2] Assistant: ${result.text}`);

    // Turn 3: Joke tool call
    console.log('\n[3] User: Tell me a joke about coding');
    result = await agent.generate('Tell me a joke about coding', {
      maxSteps: 5,
    });
    console.log(`[3] Assistant: ${result.text}`);

    // Turn 4: Goodbye
    console.log('\n[4] User: Thanks, bye!');
    result = await agent.generate('Thanks, bye!', {
      maxSteps: 5,
    });
    console.log(`[4] Assistant: ${result.text}`);

    console.log('\n' + '-'.repeat(80));
    console.log('✅ Conversation complete!');
    console.log('   Method: Mastra OTEL');
    console.log('   Service: mastra-otel-test');
    console.log('\n🔍 CHECK: PostHog should receive OTEL traces with tool calls');
    console.log('   Note: Each agent.generate() call creates a separate trace (expected behavior)');

  } catch (error) {
    console.error('\n❌ Error:', error);
    if (error instanceof Error) {
      console.error(error.stack);
    }
    process.exit(1);
  }
}

// Run the test
runConversation()
  .then(async () => {
    console.log('\n' + '='.repeat(80));

    // Flush OTEL spans before exit
    console.log('⏳ Flushing OTEL spans...');
    try {
      const provider = trace.getTracerProvider();
      if (provider && 'forceFlush' in provider && typeof provider.forceFlush === 'function') {
        await provider.forceFlush();
        console.log('✅ OTEL spans flushed');
      } else {
        // Fallback: wait 5 seconds for auto-flush
        console.log('⏳ Waiting for auto-flush (5s)...');
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    } catch (error) {
      console.error('⚠️  Error flushing OTEL spans:', error);
      // Wait a bit anyway to give SDK time to flush
      await new Promise(resolve => setTimeout(resolve, 5000));
    }

    console.log('👋 Exiting');
    process.exit(0);
  })
  .catch((error) => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
