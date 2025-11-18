#!/usr/bin/env ts-node
/**
 * Test script for PostHog LLM analytics with Vercel AI SDK + Anthropic.
 * Demonstrates the withTracing integration pattern.
 *
 * Usage:
 *     ts-node scripts/test_vercel_anthropic.ts
 *
 * Environment variables needed:
 *     ANTHROPIC_API_KEY - Your Anthropic API key (from .env file)
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { PostHog } from 'posthog-node';
import { withTracing } from '@posthog/ai';
import { generateText } from 'ai';
import { createAnthropic } from '@ai-sdk/anthropic';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables from llm-analytics-apps/.env
dotenv.config({ path: path.join(__dirname, '..', '..', '.env') });

async function main() {
  console.log('🚀 Testing PostHog LLM Analytics - Vercel AI + Anthropic\n');

  const anthropicApiKey = process.env.ANTHROPIC_API_KEY;
  const posthogApiKey = process.env.POSTHOG_API_KEY;
  const posthogHost = process.env.POSTHOG_HOST || 'https://us.i.posthog.com';

  if (!anthropicApiKey) {
    console.error('❌ Error: ANTHROPIC_API_KEY environment variable not set');
    console.log('\nPlease add to your .env file:');
    console.log('  ANTHROPIC_API_KEY=your_api_key_here\n');
    process.exit(1);
  }

  if (!posthogApiKey) {
    console.error('❌ Error: POSTHOG_API_KEY environment variable not set');
    console.log('\nPlease add to your .env file:');
    console.log('  POSTHOG_API_KEY=your_posthog_project_key\n');
    process.exit(1);
  }

  const phClient = new PostHog(
    posthogApiKey,
    {
      host: posthogHost,
      flushAt: 1,
      flushInterval: 0
    }
  );

  console.log('✅ PostHog client initialized');
  console.log(`   API Key: ${posthogApiKey.substring(0, 20)}...`);
  console.log(`   Host: ${posthogHost}\n`);

  const anthropicClient = createAnthropic({
    apiKey: anthropicApiKey,
  });

  const baseModel = anthropicClient('claude-sonnet-4-20250514');

  const model = withTracing(baseModel, phClient, {
    posthogDistinctId: 'test_user_123',
    posthogProperties: {
      conversationId: 'test_conversation_abc',
      testScript: true,
      timestamp: new Date().toISOString()
    },
    posthogPrivacyMode: true,
  });

  console.log('✅ Model wrapped with PostHog tracing');
  console.log('   Model: claude-sonnet-4-20250514');
  console.log('   Distinct ID: test_user_123');
  console.log('   Privacy Mode: enabled\n');

  console.log('📤 Sending test message to LLM...\n');

  try {
    const { text } = await generateText({
      model: model,
      prompt: 'Say "Hello from PostHog LLM analytics test!" and nothing else.'
    });

    console.log('✅ Response received:');
    console.log(`   "${text}"\n`);

    console.log('⏳ Flushing events to PostHog...');
    await phClient.shutdown();

    console.log('✅ Events flushed successfully!\n');
    console.log('🔍 Check your PostHog project for events:');
    console.log('Expected event properties:');
    console.log('   - Event: $ai_generation');
    console.log('   - Model: claude-sonnet-4-20250514');
    console.log('   - Distinct ID: test_user_123');
    console.log('   - conversationId: test_conversation_abc');
    console.log('   - Privacy mode: true (prompts/responses hidden)\n');

  } catch (error: any) {
    console.error('❌ Error during test:', error.message);
    if (error.stack) {
      console.error(error.stack);
    }
    await phClient.shutdown();
    process.exit(1);
  }
}

main().catch(console.error);
