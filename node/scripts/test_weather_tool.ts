#!/usr/bin/env ts-node
/**
 * Test script for weather tool functionality.
 * Tests that providers correctly call the weather API with lat/lon/location_name.
 *
 * Usage:
 *     ts-node test_weather_tool.ts                      # Run all tests
 *     ts-node test_weather_tool.ts --provider anthropic # Test specific provider
 *     ts-node test_weather_tool.ts --list               # List available providers
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { PostHog } from 'posthog-node';
import { AnthropicProvider } from '../dist/providers/anthropic.js';
import { AnthropicStreamingProvider } from '../dist/providers/anthropic-streaming.js';
import { GeminiProvider } from '../dist/providers/gemini.js';
import { GeminiStreamingProvider } from '../dist/providers/gemini-streaming.js';
import { LangChainProvider } from '../dist/providers/langchain.js';
import { OpenAIProvider } from '../dist/providers/openai.js';
import { OpenAIChatProvider } from '../dist/providers/openai-chat.js';
import { OpenAIChatStreamingProvider } from '../dist/providers/openai-chat-streaming.js';
import { OpenAIStreamingProvider } from '../dist/providers/openai-streaming.js';
import { VercelAIProvider } from '../dist/providers/vercel-ai.js';
import { VercelAIStreamingProvider } from '../dist/providers/vercel-ai-streaming.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables
dotenv.config({ path: path.join(__dirname, '..', '..', '.env') });

// Define available providers
interface ProviderConfig {
  class: any;
  name: string;
  isStreaming: boolean;
  requiresThinking?: boolean;
}

const AVAILABLE_PROVIDERS: Record<string, ProviderConfig> = {
  'anthropic': {
    class: AnthropicProvider,
    name: 'Anthropic Provider',
    isStreaming: false,
    requiresThinking: true
  },
  'anthropic-streaming': {
    class: AnthropicStreamingProvider,
    name: 'Anthropic Streaming Provider',
    isStreaming: true,
    requiresThinking: true
  },
  'gemini': {
    class: GeminiProvider,
    name: 'Google Gemini Provider',
    isStreaming: false
  },
  'gemini-streaming': {
    class: GeminiStreamingProvider,
    name: 'Google Gemini Streaming Provider',
    isStreaming: true
  },
  'openai': {
    class: OpenAIProvider,
    name: 'OpenAI Responses API Provider',
    isStreaming: false
  },
  'openai-streaming': {
    class: OpenAIStreamingProvider,
    name: 'OpenAI Responses API Streaming Provider',
    isStreaming: true
  },
  'openai-chat': {
    class: OpenAIChatProvider,
    name: 'OpenAI Chat Completions Provider',
    isStreaming: false
  },
  'openai-chat-streaming': {
    class: OpenAIChatStreamingProvider,
    name: 'OpenAI Chat Completions Streaming Provider',
    isStreaming: true
  },
  'langchain': {
    class: LangChainProvider,
    name: 'LangChain Provider',
    isStreaming: false
  },
  'vercel-ai': {
    class: VercelAIProvider,
    name: 'Vercel AI SDK Provider',
    isStreaming: false
  },
  'vercel-ai-streaming': {
    class: VercelAIStreamingProvider,
    name: 'Vercel AI SDK Streaming Provider',
    isStreaming: true
  },
};

function initPostHog(): PostHog | null {
  const posthogApiKey = process.env.POSTHOG_API_KEY;
  const posthogHost = process.env.POSTHOG_HOST || 'https://us.i.posthog.com';

  if (!posthogApiKey) {
    console.log('⚠️  Warning: POSTHOG_API_KEY not set, analytics will not be tracked');
    return null;
  }

  return new PostHog(posthogApiKey, {
    host: posthogHost,
    flushAt: 1,
    flushInterval: 0
  });
}

async function testProvider(
  providerClass: any,
  providerName: string,
  useStreaming: boolean,
  requiresThinking: boolean = false
): Promise<boolean> {
  console.log(`\n${'='.repeat(80)}`);
  console.log(`🧪 Testing ${providerName}`);
  console.log(`${'='.repeat(80)}\n`);

  // Initialize PostHog
  const posthogClient = initPostHog();

  if (!posthogClient) {
    console.log('❌ Cannot run test without PostHog client');
    return false;
  }

  // Initialize provider (handle Anthropic's different constructor signature)
  const provider = requiresThinking
    ? new providerClass(posthogClient, false, undefined, null)
    : new providerClass(posthogClient, null);

  // Test query
  const testQuery = "What's the weather in Dublin, Ireland?";
  console.log(`📝 Query: ${testQuery}\n`);

  try {
    let response: string;

    if (useStreaming) {
      console.log('🔄 Streaming response:\n');
      let fullResponse = '';
      const stream = provider.chatStream(testQuery);

      for await (const chunk of stream) {
        process.stdout.write(chunk);
        fullResponse += chunk;
      }
      console.log('\n');
      response = fullResponse;
    } else {
      console.log('💬 Response:\n');
      response = await provider.chat(testQuery);
      console.log(response);
      console.log();
    }

    // Check if response contains weather data
    if (response.includes('°C') || response.includes('°F')) {
      console.log('✅ Test PASSED - Weather data received!');

      // Check if location name is used
      if (response.includes('Dublin')) {
        console.log('✅ Location name displayed correctly!');
      } else {
        console.log('⚠️  Warning: Location name might not be displayed');
      }

      return true;
    } else {
      console.log('❌ Test FAILED - No weather data in response');
      return false;
    }

  } catch (error: any) {
    console.log(`❌ Test FAILED with error: ${error.message}`);
    console.error(error.stack);
    return false;
  } finally {
    // Shutdown PostHog
    if (posthogClient) {
      await posthogClient.shutdown();
    }
  }
}

function listProviders(): void {
  console.log(`\n${'='.repeat(80)}`);
  console.log('📋 Available Providers');
  console.log(`${'='.repeat(80)}\n`);

  for (const [key, config] of Object.entries(AVAILABLE_PROVIDERS)) {
    const streamIndicator = config.isStreaming ? ' (streaming)' : '';
    console.log(`  • ${key.padEnd(25)} - ${config.name}${streamIndicator}`);
  }

  console.log();
}

async function main() {
  const args = process.argv.slice(2);

  // Parse arguments
  let specificProvider: string | null = null;
  let showList = false;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--provider' || args[i] === '-p') {
      specificProvider = args[i + 1];
      i++;
    } else if (args[i] === '--list' || args[i] === '-l') {
      showList = true;
    }
  }

  // Handle --list flag
  if (showList) {
    listProviders();
    process.exit(0);
  }

  // Validate provider if specified
  if (specificProvider && !AVAILABLE_PROVIDERS[specificProvider]) {
    console.error(`❌ Unknown provider: ${specificProvider}`);
    console.log('\nAvailable providers:');
    listProviders();
    process.exit(1);
  }

  console.log(`\n${'='.repeat(80)}`);
  console.log('🚀 Weather Tool Test Suite');
  console.log(`${'='.repeat(80)}`);

  const results: Array<[string, boolean]> = [];

  // Determine which providers to test
  const providersToTest = specificProvider
    ? { [specificProvider]: AVAILABLE_PROVIDERS[specificProvider] }
    : AVAILABLE_PROVIDERS;

  // Run tests
  for (const [key, config] of Object.entries(providersToTest)) {
    const passed = await testProvider(
      config.class,
      config.name,
      config.isStreaming,
      config.requiresThinking
    );
    results.push([key, passed]);
  }

  // Print summary
  console.log(`\n${'='.repeat(80)}`);
  console.log('📊 Test Summary');
  console.log(`${'='.repeat(80)}\n`);

  for (const [name, passed] of results) {
    const status = passed ? '✅ PASS' : '❌ FAIL';
    console.log(`${status} - ${name}`);
  }

  const totalPassed = results.filter(([_, passed]) => passed).length;
  const totalTests = results.length;

  console.log(`\nTotal: ${totalPassed}/${totalTests} tests passed`);

  // Exit with appropriate code
  process.exit(totalPassed === totalTests ? 0 : 1);
}

main().catch(console.error);
