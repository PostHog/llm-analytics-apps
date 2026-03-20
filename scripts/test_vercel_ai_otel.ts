#!/usr/bin/env npx tsx
/**
 * E2E test script for OTel -> PostHog mapping with Vercel AI SDK.
 *
 * Runs real Vercel AI SDK scenarios and sends OTel spans to PostHog for manual
 * verification. Each scenario exercises a different feature of the framework.
 *
 * Usage:
 *   npx tsx scripts/test_vercel_ai_otel.ts           # Run all scenarios
 *   npx tsx scripts/test_vercel_ai_otel.ts 2          # Run scenario 2 only
 *   npx tsx scripts/test_vercel_ai_otel.ts 2 5 8      # Run scenarios 2, 5, and 8
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { generateText, streamText, generateObject } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '..', '.env') });

const MODEL = 'gpt-4o-mini';

let otelSdk: NodeSDK | null = null;

function setupOtel(): NodeSDK {
  const posthogApiKey = process.env.POSTHOG_API_KEY;
  const posthogHost = process.env.POSTHOG_HOST || 'http://localhost:8010';
  const debug = process.env.DEBUG === '1';

  if (!posthogApiKey) {
    console.error('ERROR: POSTHOG_API_KEY must be set in .env');
    process.exit(1);
  }

  const resourceAttrs: Record<string, string> = {
    'service.name': 'vercel-ai-otel-test',
    'user.id': process.env.POSTHOG_DISTINCT_ID || 'otel-test-user',
  };
  if (debug) {
    resourceAttrs['posthog.ai.debug'] = 'true';
  }

  const exporter = new OTLPTraceExporter({
    url: `${posthogHost}/i/v0/ai/otel`,
    headers: {
      Authorization: `Bearer ${posthogApiKey}`,
    },
  });

  const sdk = new NodeSDK({
    resource: resourceFromAttributes(resourceAttrs),
    traceExporter: exporter,
  });
  sdk.start();
  return sdk;
}

function header(num: number, title: string): void {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`  Scenario ${num}: ${title}`);
  console.log('='.repeat(60));
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createModel() {
  const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY! });
  return openai(MODEL);
}

function telemetry(functionId: string, extra: Record<string, string> = {}) {
  const metadata: Record<string, string> = {
    posthog_distinct_id: process.env.POSTHOG_DISTINCT_ID || 'otel-test-user',
    provider: 'vercel-ai-sdk-raw-otel',
    ...extra,
  };
  return {
    isEnabled: true,
    functionId,
    metadata,
  };
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

async function test1SimpleGreeting(): Promise<void> {
  header(1, 'Simple greeting (no tools)');
  const { text } = await generateText({
    model: createModel(),
    system: 'You are a friendly assistant.',
    prompt: 'Hi, how are you?',
    experimental_telemetry: telemetry('test-simple-greeting'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

async function test2SingleToolCall(): Promise<void> {
  header(2, 'Single tool call (weather)');
  const { text } = await generateText({
    model: createModel(),
    system: 'You help with weather.',
    prompt: "What's the weather in Paris, France?",
    tools: {
      get_weather: {
        description: 'Get current weather for a location.',
        inputSchema: z.object({
          latitude: z.number(),
          longitude: z.number(),
          location_name: z.string(),
        }),
        execute: async ({ location_name }) => {
          return `Weather in ${location_name}: 15°C, sunny`;
        },
      },
    },
    maxSteps: 3,
    experimental_telemetry: telemetry('test-single-tool'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

async function test3MultipleToolCalls(): Promise<void> {
  header(3, 'Multiple tool calls in one turn');
  const { text } = await generateText({
    model: createModel(),
    system: 'You help with weather.',
    prompt: 'Compare the weather in Tokyo and London right now.',
    tools: {
      get_weather: {
        description: 'Get current weather for a location.',
        inputSchema: z.object({
          latitude: z.number(),
          longitude: z.number(),
          location_name: z.string(),
        }),
        execute: async ({ location_name }) => {
          return `Weather in ${location_name}: 15°C, sunny`;
        },
      },
    },
    maxSteps: 3,
    experimental_telemetry: telemetry('test-multiple-tools'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

async function test4StructuredOutput(): Promise<void> {
  header(4, 'Structured output (generateObject)');

  const { object } = await generateObject({
    model: createModel(),
    prompt: 'Tell me about Montreal, Canada.',
    schema: z.object({
      name: z.string(),
      country: z.string(),
      population_estimate: z.string(),
      fun_fact: z.string(),
    }),
    experimental_telemetry: telemetry('test-structured-output'),
  });
  console.log(`  Result: ${JSON.stringify(object)}`);
}

async function test5ToolErrorHandling(): Promise<void> {
  header(5, 'Tool that raises an error');
  const { text } = await generateText({
    model: createModel(),
    system: 'You help with calculations.',
    prompt: 'What is 10 divided by 0?',
    tools: {
      divide: {
        description: 'Divide two numbers.',
        inputSchema: z.object({
          a: z.number(),
          b: z.number(),
        }),
        execute: async ({ a, b }) => {
          if (b === 0) {
            throw new Error('Cannot divide by zero');
          }
          return String(a / b);
        },
      },
    },
    maxSteps: 3,
    experimental_telemetry: telemetry('test-tool-error'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

async function test6MinimalInvocation(): Promise<void> {
  header(6, 'Minimal invocation (no tools, no system prompt)');
  const { text } = await generateText({
    model: createModel(),
    prompt: 'What is 2 + 2?',
    experimental_telemetry: telemetry('test-minimal'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

async function test7MultiTurn(): Promise<void> {
  header(7, 'Multi-turn conversation');
  const messages: Array<{ role: 'system' | 'user' | 'assistant'; content: string }> = [
    { role: 'system', content: 'You are a helpful assistant.' },
    { role: 'user', content: 'My name is Carlos.' },
  ];

  const result1 = await generateText({
    model: createModel(),
    messages,
    experimental_telemetry: telemetry('test-multi-turn-1'),
  });
  console.log(`  Turn 1: ${result1.text.slice(0, 120)}`);

  messages.push({ role: 'assistant', content: result1.text });
  messages.push({ role: 'user', content: "What's my name?" });

  const result2 = await generateText({
    model: createModel(),
    messages,
    experimental_telemetry: telemetry('test-multi-turn-2'),
  });
  console.log(`  Turn 2: ${result2.text.slice(0, 120)}`);
}

async function test8MultipleTools(): Promise<void> {
  header(8, 'Multiple different tools available');
  const { text } = await generateText({
    model: createModel(),
    system: 'You are a helpful assistant with weather and joke tools.',
    prompt: 'Tell me a joke about the weather.',
    tools: {
      get_weather: {
        description: 'Get current weather for a location.',
        inputSchema: z.object({
          latitude: z.number(),
          longitude: z.number(),
          location_name: z.string(),
        }),
        execute: async ({ location_name }) => {
          return `Weather in ${location_name}: 15°C, sunny`;
        },
      },
      tell_joke: {
        description: 'Tell a joke with a setup and punchline.',
        inputSchema: z.object({
          setup: z.string(),
          punchline: z.string(),
        }),
        execute: async ({ setup, punchline }) => {
          return `${setup}\n\n${punchline}`;
        },
      },
    },
    maxSteps: 3,
    experimental_telemetry: telemetry('test-multiple-tools-available'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

async function test9Streaming(): Promise<void> {
  header(9, 'Streaming response');
  const result = streamText({
    model: createModel(),
    system: 'You are a travel expert. Be concise.',
    prompt: 'What are the top 3 things to do in Montreal?',
    experimental_telemetry: telemetry('test-streaming'),
  });

  let fullText = '';
  for await (const chunk of result.textStream) {
    fullText += chunk;
  }
  console.log(`  Response: ${fullText.slice(0, 120)}`);
}

async function test10AnthropicProvider(): Promise<void> {
  header(10, 'Different provider (Anthropic via Vercel AI SDK)');

  if (!process.env.ANTHROPIC_API_KEY) {
    console.log('  SKIPPED: ANTHROPIC_API_KEY not set');
    return;
  }

  const { createAnthropic } = await import('@ai-sdk/anthropic');
  const anthropic = createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY! });
  const { text } = await generateText({
    model: anthropic('claude-sonnet-4-5-20250929'),
    system: 'Be brief.',
    prompt: 'Say hello in French.',
    experimental_telemetry: telemetry('test-anthropic-provider'),
  });
  console.log(`  Response: ${text.slice(0, 120)}`);
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

const SCENARIOS: Map<number, [string, () => Promise<void>]> = new Map([
  [1, ['Simple greeting', test1SimpleGreeting]],
  [2, ['Single tool call', test2SingleToolCall]],
  [3, ['Multiple tool calls', test3MultipleToolCalls]],
  [4, ['Structured output', test4StructuredOutput]],
  [5, ['Tool error handling', test5ToolErrorHandling]],
  [6, ['Minimal invocation', test6MinimalInvocation]],
  [7, ['Multi-turn', test7MultiTurn]],
  [8, ['Multiple tools', test8MultipleTools]],
  [9, ['Streaming', test9Streaming]],
  [10, ['Anthropic provider', test10AnthropicProvider]],
]);

async function main(): Promise<void> {
  otelSdk = setupOtel();

  const debug = process.env.DEBUG === '1';
  const host = process.env.POSTHOG_HOST || 'http://localhost:8010';

  console.log('Vercel AI SDK OTel -> PostHog E2E Test');
  console.log(`  PostHog host: ${host}`);
  console.log(`  Debug mode:   ${debug}`);
  console.log(`  Model:        ${MODEL}`);

  const args = process.argv.slice(2);
  const ids: number[] = args.length > 0 ? args.map(Number) : [...SCENARIOS.keys()];

  for (const scenarioId of ids) {
    const scenario = SCENARIOS.get(scenarioId);
    if (!scenario) {
      console.log(`\nUnknown scenario: ${scenarioId}`);
      continue;
    }
    const [, fn] = scenario;
    try {
      await fn();
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      console.log(`  FAILED: ${err.constructor.name}: ${err.message}`);
    }
  }

  await otelSdk.shutdown();

  console.log(`\n${'='.repeat(60)}`);
  console.log('  All done! Check PostHog -> LLM analytics -> Traces');
  console.log('='.repeat(60) + '\n');
}

main().catch((e) => {
  console.error('Fatal error:', e);
  process.exit(1);
});
