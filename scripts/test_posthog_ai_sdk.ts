#!/usr/bin/env npx tsx
/**
 * Smoke test for the restructured @posthog/ai package (subpath imports +
 * optional peer dependencies). See PostHog/posthog-js#3739.
 *
 * Each provider client now ships under its own subpath, and you install only
 * the provider SDK you actually use:
 *   - @posthog/ai/openai     (peer: openai)
 *   - @posthog/ai/anthropic  (peer: @anthropic-ai/sdk)
 * The SDK-agnostic primitive captureAiGeneration stays on the root export and
 * needs no provider SDK.
 *
 * Usage:
 *   npx tsx scripts/test_posthog_ai_sdk.ts            # run every applicable demo
 *
 * Demos requiring a provider key are skipped when the key is absent;
 * captureAiGeneration always runs since it makes no network call to a provider.
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { PostHog } from 'posthog-node';
import { OpenAI } from '@posthog/ai/openai';
import { Anthropic } from '@posthog/ai/anthropic';
import { captureAiGeneration } from '@posthog/ai';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '..', '.env') });

const DISTINCT_ID = process.env.POSTHOG_DISTINCT_ID || 'posthog-ai-sdk-test';

function header(title: string): void {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`  ${title}`);
  console.log('='.repeat(60));
}

async function demoOpenAI(phClient: PostHog): Promise<void> {
  header('@posthog/ai/openai — wrapped OpenAI client');
  if (!process.env.OPENAI_API_KEY) {
    console.log('  SKIPPED: OPENAI_API_KEY not set');
    return;
  }

  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY, posthog: phClient });
  const completion = await client.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [{ role: 'user', content: 'Reply with exactly: pong' }],
    posthogDistinctId: DISTINCT_ID,
    posthogProperties: { source: 'test_posthog_ai_sdk', integration: 'openai-subpath' },
  });
  console.log(`  Response: ${completion.choices[0]?.message?.content}`);
}

async function demoAnthropic(phClient: PostHog): Promise<void> {
  header('@posthog/ai/anthropic — wrapped Anthropic client');
  if (!process.env.ANTHROPIC_API_KEY) {
    console.log('  SKIPPED: ANTHROPIC_API_KEY not set');
    return;
  }

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY, posthog: phClient });
  const message = await client.messages.create({
    model: 'claude-sonnet-4-5-20250929',
    max_tokens: 32,
    messages: [{ role: 'user', content: 'Reply with exactly: pong' }],
    posthogDistinctId: DISTINCT_ID,
    posthogProperties: { source: 'test_posthog_ai_sdk', integration: 'anthropic-subpath' },
  });
  if (!('content' in message)) {
    console.log('  (unexpected streamed response)');
    return;
  }
  const block = message.content[0];
  console.log(`  Response: ${block?.type === 'text' ? block.text : '<non-text>'}`);
}

async function demoCaptureAiGeneration(phClient: PostHog): Promise<void> {
  header('captureAiGeneration — custom/unsupported provider');

  const start = Date.now();
  const messages = [{ role: 'user', content: 'Summarize PostHog in one word.' }];
  const output = 'Observability';

  await captureAiGeneration(phClient, {
    distinctId: DISTINCT_ID,
    traceId: 'posthog-ai-sdk-test-trace',
    provider: 'custom-http-provider',
    model: 'made-up-model-v1',
    input: messages,
    output,
    modelParameters: { temperature: 0.2 },
    usage: { inputTokens: 12, outputTokens: 1 },
    latency: (Date.now() - start) / 1000,
    properties: { source: 'test_posthog_ai_sdk', integration: 'captureAiGeneration' },
  });
  console.log(`  Captured $ai_generation for custom provider (output: "${output}")`);
}

async function main(): Promise<void> {
  const projectToken = process.env.POSTHOG_API_KEY;
  const host = process.env.POSTHOG_HOST || 'https://us.i.posthog.com';

  if (!projectToken) {
    console.error('ERROR: POSTHOG_API_KEY must be set in .env');
    process.exit(1);
  }

  console.log('@posthog/ai subpath + captureAiGeneration smoke test');
  console.log(`  PostHog host: ${host}`);
  console.log(`  Distinct ID:  ${DISTINCT_ID}`);

  const phClient = new PostHog(projectToken, { host, flushAt: 1, flushInterval: 0 });

  for (const demo of [demoOpenAI, demoAnthropic, demoCaptureAiGeneration]) {
    try {
      await demo(phClient);
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      console.log(`  FAILED: ${err.constructor.name}: ${err.message}`);
    }
  }

  await phClient.shutdown();

  console.log(`\n${'='.repeat(60)}`);
  console.log('  Done. Check PostHog -> LLM analytics -> Traces');
  console.log('='.repeat(60) + '\n');
}

main().catch((e) => {
  console.error('Fatal error:', e);
  process.exit(1);
});
