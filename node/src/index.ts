#!/usr/bin/env node

import * as dotenv from 'dotenv';
import * as readline from 'readline';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { PostHog } from 'posthog-node';
import { AnthropicProvider } from './providers/anthropic.js';
import { AnthropicStreamingProvider } from './providers/anthropic-streaming.js';
import { GeminiProvider } from './providers/gemini.js';
import { GeminiStreamingProvider } from './providers/gemini-streaming.js';
import { LangChainProvider } from './providers/langchain.js';
import { OpenAIProvider } from './providers/openai.js';
import { OpenAIChatProvider } from './providers/openai-chat.js';
import { OpenAIChatStreamingProvider } from './providers/openai-chat-streaming.js';
import { OpenAIStreamingProvider } from './providers/openai-streaming.js';
import { VercelAIProvider } from './providers/vercel-ai.js';
import { VercelAIStreamingProvider } from './providers/vercel-ai-streaming.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '..', '..', '.env') });

const posthog = new PostHog(
  process.env.POSTHOG_API_KEY!,
  { 
    host: process.env.POSTHOG_HOST || 'https://app.posthog.com',
    flushAt: 1,  // Flush after every event
    flushInterval: 0  // Don't wait for interval, flush immediately
  }
);

// Enable debug mode to see PostHog events
// posthog.debug();

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function clearScreen(): void {
  if (process.env.DEBUG !== '1') {
    console.clear();
  }
}

async function selectMode(): Promise<string> {
  const modes = new Map<string, string>([
    ['1', 'Chat Mode'],
    ['2', 'Tool Call Test'],
    ['3', 'Message Test'],
    ['4', 'Image Test'],
    ['5', 'Embeddings Test']
  ]);

  console.log('\nSelect Mode:');
  console.log('='.repeat(50));
  for (const [key, name] of modes) {
    if (key === '1') {
      console.log(`  ${key}. ${name} (Interactive conversation)`);
    } else if (key === '2') {
      console.log(`  ${key}. ${name} (Auto-test: Weather in Montreal)`);
    } else if (key === '3') {
      console.log(`  ${key}. ${name} (Auto-test: Simple greeting)`);
    } else if (key === '4') {
      console.log(`  ${key}. ${name} (Auto-test: Describe image)`);
    } else if (key === '5') {
      console.log(`  ${key}. ${name} (Auto-test: Generate embeddings)`);
    }
  }
  console.log('='.repeat(50));

  return new Promise((resolve) => {
    const askForMode = () => {
      rl.question('\nSelect a mode (1-5) or \'q\' to quit: ', (choice) => {
        choice = choice.trim().toLowerCase();
        if (['1', '2', '3', '4', '5'].includes(choice)) {
          clearScreen();
          resolve(choice);
        } else if (choice === 'q') {
          console.log('\n👋 Goodbye!');
          cleanup();
        } else {
          console.log('❌ Invalid choice. Please select 1, 2, 3, 4, or 5.');
          askForMode();
        }
      });
    };
    askForMode();
  });
}

function displayProviders(mode?: string): Map<string, string> {
  let providers = new Map<string, string>([
    ['1', 'Anthropic'],
    ['2', 'Anthropic Streaming'],
    ['3', 'Google Gemini'],
    ['4', 'Google Gemini Streaming'],
    ['5', 'LangChain (OpenAI)'],
    ['6', 'OpenAI Responses'],
    ['7', 'OpenAI Responses Streaming'],
    ['8', 'OpenAI Chat Completions'],
    ['9', 'OpenAI Chat Completions Streaming']
  ]);

  // Filter providers for embeddings mode
  if (mode === '5') {
    // Only OpenAI providers support embeddings
    providers = new Map<string, string>([
      ['6', 'OpenAI Responses'],
      ['7', 'OpenAI Responses Streaming'],
      ['8', 'OpenAI Chat Completions'],
      ['9', 'OpenAI Chat Completions Streaming']
    ]);
  }

  console.log('\nAvailable AI Providers:');
  console.log('='.repeat(50));
  for (const [key, name] of providers) {
    console.log(`  ${key}. ${name}`);
  }
  console.log('='.repeat(50));

  return providers;
}

async function getProviderChoice(allowModeChange: boolean = false, allowAll: boolean = false): Promise<string> {
  return new Promise((resolve) => {
    const askForChoice = () => {
      let prompt = '\nSelect a provider (1-9)';
      if (allowAll) {
        prompt += ', \'a\' for all providers';
      }
      if (allowModeChange) {
        prompt += ', or \'m\' to change mode';
      }
      prompt += ': ';
      
      rl.question(prompt, (choice) => {
        choice = choice.trim().toLowerCase();
        if (['1', '2', '3', '4', '5', '6', '7', '8', '9'].includes(choice)) {
          clearScreen();
          resolve(choice);
        } else if (allowAll && choice === 'a') {
          clearScreen();
          resolve('all');
        } else if (allowModeChange && choice === 'm') {
          clearScreen();
          resolve('mode_change');
        } else {
          console.log('❌ Invalid choice. Please select a valid option.');
          askForChoice();
        }
      });
    };
    askForChoice();
  });
}

function createProvider(choice: string): any {
  switch (choice) {
    case '1':
      return new AnthropicProvider(posthog);
    case '2':
      return new AnthropicStreamingProvider(posthog);
    case '3':
      return new GeminiProvider(posthog);
    case '4':
      return new GeminiStreamingProvider(posthog);
    case '5':
      return new LangChainProvider(posthog);
    case '6':
      return new OpenAIProvider(posthog);
    case '7':
      return new OpenAIStreamingProvider(posthog);
    case '8':
      return new OpenAIChatProvider(posthog);
    case '9':
      return new OpenAIChatStreamingProvider(posthog);
    default:
      throw new Error('Invalid provider choice');
  }
}

async function runChat(provider: any): Promise<boolean> {
  console.log(`\n🤖 Welcome to the chatbot using ${provider.getName()}!`);
  console.log('🌤️ All providers have weather tools - just ask about weather in any city!');

  if (provider.getDescription) {
    console.log(provider.getDescription());
  }

  console.log('Type your messages below. Type \'q\' to return to provider selection.\n');

  return new Promise((resolve) => {
    const chat = () => {
      rl.question('👤 You: ', async (userInput) => {
        userInput = userInput.trim();

        if (!userInput) {
          chat();
          return;
        }

        // Check for quit command to return to provider selection
        if (userInput.toLowerCase() === 'q') {
          console.log('\n↩️  Returning to provider selection...\n');
          resolve(true);
          return;
        }

        try {
          // Check if provider supports streaming
          if (provider.chatStream && typeof provider.chatStream === 'function') {
            process.stdout.write('\n🤖 Bot: ');
            for await (const chunk of provider.chatStream(userInput)) {
              process.stdout.write(chunk);
            }
            console.log(); // New line after streaming completes
            console.log('─'.repeat(50));
          } else {
            const response = await provider.chat(userInput);
            console.log(`\n🤖 Bot: ${response}`);
            console.log('─'.repeat(50));
          }
        } catch (error: any) {
          logError(error);
          console.log('─'.repeat(50));
        }

        chat();
      });
    };

    chat();
  });
}

async function runToolCallTest(provider: any): Promise<{ success: boolean; error: string | null }> {
  const testQuery = 'What is the weather in Montreal, Canada?';
  
  console.log(`\nTool Call Test: ${provider.getName()}`);
  console.log('-'.repeat(50));
  console.log(`Query: "${testQuery}"`);
  console.log();
  
  try {
    // Reset conversation for clean test
    provider.resetConversation();
    
    // Send the test query
    const response = await provider.chat(testQuery);
    
    console.log(`Response: ${response}`);
    console.log();
    return { success: true, error: null };
  } catch (error: any) {
    logError(error);
    return { success: false, error: error.message };
  }
}

async function runMessageTest(provider: any): Promise<{ success: boolean; error: string | null }> {
  const testQuery = 'Hi, how are you today?';
  
  console.log(`\nMessage Test: ${provider.getName()}`);
  console.log('-'.repeat(50));
  console.log(`Query: "${testQuery}"`);
  console.log();
  
  try {
    // Reset conversation for clean test
    provider.resetConversation();
    
    // Send the test query
    const response = await provider.chat(testQuery);
    
    console.log(`Response: ${response}`);
    console.log();
    return { success: true, error: null };
  } catch (error: any) {
    logError(error);
    return { success: false, error: error.message };
  }
}

async function runEmbeddingsTest(provider: any): Promise<{ success: boolean; error: string | null }> {
  const testTexts = [
    'The quick brown fox jumps over the lazy dog.'
  ];

  console.log(`\nEmbeddings Test: ${provider.getName()}`);
  console.log('-'.repeat(50));

  // Check if provider supports embeddings
  if (!provider.embed || typeof provider.embed !== 'function') {
    console.log(`❌ ${provider.getName()} does not support embeddings`);
    return { success: false, error: 'Provider does not support embeddings' };
  }

  try {
    for (let i = 0; i < testTexts.length; i++) {
      const text = testTexts[i];
      console.log(`\nTest ${i + 1}: "${text}"`);

      // Generate embeddings
      const embedding = await provider.embed(text);

      if (embedding && embedding.length > 0) {
        console.log(`✅ Generated embedding with ${embedding.length} dimensions`);
        // Show first 5 values as sample
        console.log(`   Sample values: [${embedding.slice(0, 5).join(', ')}]...`);
      } else {
        console.log(`❌ Failed to generate embedding`);
        return { success: false, error: `Failed to generate embedding for text ${i + 1}` };
      }
    }

    console.log();
    return { success: true, error: null };

  } catch (error: any) {
    logError(error);
    return { success: false, error: error.message };
  }
}

async function runImageTest(provider: any): Promise<{ success: boolean; error: string | null }> {
  // Create a simple test image (1x1 red pixel as base64)
  const base64Image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==';
  const testQuery = 'What do you see in this image? Please describe it.';
  
  console.log(`\nImage Test: ${provider.getName()}`);
  console.log('-'.repeat(50));
  console.log(`Query: "${testQuery}"`);
  console.log(`Image: 1x1 red pixel (base64 encoded)`);
  console.log();
  
  try {
    // Reset conversation for clean test
    provider.resetConversation();
    
    // Send the test query with image
    const response = await provider.chat(testQuery, base64Image);
    
    console.log(`Response: ${response}`);
    console.log();
    return { success: true, error: null };
  } catch (error: any) {
    logError(error);
    return { success: false, error: error.message };
  }
}

async function runAllTests(mode: string): Promise<void> {
  let providersInfo: Array<[string, string]> = [
    ['1', 'Anthropic'],
    ['2', 'Anthropic Streaming'],
    ['3', 'Google Gemini'],
    ['4', 'Google Gemini Streaming'],
    ['5', 'LangChain (OpenAI)'],
    ['6', 'OpenAI Responses'],
    ['7', 'OpenAI Responses Streaming'],
    ['8', 'OpenAI Chat Completions']
  ];

  // Filter providers for embeddings test (only those that support it)
  if (mode === '5') {
    // Only OpenAI providers support embeddings
    providersInfo = [
      ['6', 'OpenAI Responses'],
      ['7', 'OpenAI Responses Streaming'],
      ['8', 'OpenAI Chat Completions']
    ];
  }
  
  const testName = mode === '2' ? 'Tool Call Test' : 
                   mode === '3' ? 'Message Test' : 
                   mode === '4' ? 'Image Test' : 
                   mode === '5' ? 'Embeddings Test' : 'Unknown Test';
  console.log(`\n🔄 Running ${testName} on all providers...`);
  console.log('='.repeat(60));
  console.log();
  
  interface TestResult {
    name: string;
    success: boolean;
    error: string | null;
  }
  
  const results: TestResult[] = [];
  
  for (const [providerId, providerName] of providersInfo) {
    console.log(`[${providerId}/8] Testing ${providerName}...`);
    
    try {
      const provider = createProvider(providerId);
      
      // Run the appropriate test
      const result = mode === '2' 
        ? await runToolCallTest(provider)
        : mode === '3'
        ? await runMessageTest(provider)
        : mode === '4'
        ? await runImageTest(provider)
        : mode === '5'
        ? await runEmbeddingsTest(provider)
        : { success: false, error: 'Unknown test mode' };
      
      results.push({
        name: providerName,
        success: result.success,
        error: result.error
      });
      
    } catch (initError: any) {
      console.log(`   ❌ Failed to initialize: ${initError.message}`);
      results.push({
        name: providerName,
        success: false,
        error: `Initialization failed: ${initError.message}`
      });
    }
  }
  
  // Print summary
  console.log('\n' + '='.repeat(60));
  console.log(`📊 ${testName} Summary`);
  console.log('='.repeat(60));
  
  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);
  
  console.log(`\n✅ Successful: ${successful.length}/${results.length}`);
  for (const result of successful) {
    console.log(`   • ${result.name}`);
  }
  
  if (failed.length > 0) {
    console.log(`\n❌ Failed: ${failed.length}/${results.length}`);
    for (const result of failed) {
      console.log(`   • ${result.name}`);
      console.log(`     Error: ${result.error}`);
    }
  }
  
  console.log('='.repeat(60));
  console.log();
}

async function main(): Promise<void> {
  clearScreen();
  console.log('\n🚀 Unified AI Chatbot');
  console.log('Choose your mode and AI provider');
  console.log();
  
  // First, select the mode
  let mode = await selectMode();
  
  // Main loop for provider selection and testing
  while (true) {
    // Display providers and get user choice
    displayProviders(mode);
    
    // Allow mode change for all modes, 'all' option only for test modes
    const allowModeChange = (mode === '1' || mode === '2' || mode === '3' || mode === '4' || mode === '5');
    const allowAll = (mode === '2' || mode === '3' || mode === '4' || mode === '5');
    const choice = await getProviderChoice(allowModeChange, allowAll);
    
    // Check if user wants to change mode
    if (choice === 'mode_change') {
      mode = await selectMode();
      continue;
    }
    
    // Check if user wants to test all providers
    if (choice === 'all') {
      await runAllTests(mode);
      continue;
    }
    
    // Create provider instance
    let provider;
    try {
      provider = createProvider(choice);
      console.log(`\n✅ Initialized ${provider.getName()}`);
    } catch (error: any) {
      console.log(`❌ Failed to initialize provider: ${error.message}`);
      continue;
    }
    
    // Execute based on mode
    if (mode === '1') {
      // Chat Mode - run interactive chat and continue when done
      await runChat(provider);
      continue;
    } else if (mode === '2') {
      // Tool Call Test - run test and loop back
      const result = await runToolCallTest(provider);
      if (!result.error) {
        console.log();
      }
    } else if (mode === '3') {
      // Message Test - run test and loop back
      const result = await runMessageTest(provider);
      if (!result.error) {
        console.log();
      }
    } else if (mode === '4') {
      // Image Test - run test and loop back
      const result = await runImageTest(provider);
      if (!result.error) {
        console.log();
      }
    } else if (mode === '5') {
      // Embeddings Test - run test and loop back
      const result = await runEmbeddingsTest(provider);
      if (!result.error) {
        console.log();
      }
    }
  }
}

const cleanup = async () => {
  try {
    console.log('\n\n👋 Goodbye!');
    console.log('Shutting down PostHog client...');
    rl.close();
    await posthog.shutdown();
    console.log('✅ PostHog client shut down successfully');
  } catch (error) {
    console.error('❌ Error shutting down PostHog client:', error);
  }
  process.exit(0);
};

const logError = (error: unknown) => {
  if (error instanceof Error) {
    console.log(`❌ Error: ${error.stack}`);
  } else {
    console.error('❌ Error:', error);
  }
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('SIGQUIT', cleanup);

main().catch(async (error) => {
  console.error('Fatal error:', error);
  rl.close();
  await posthog.shutdown();
  process.exit(1);
});