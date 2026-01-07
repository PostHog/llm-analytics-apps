#!/usr/bin/env node
/**
 * Test script to reproduce file parts error with withTracing
 *
 * Issue: "Cannot convert undefined or null to object" when using file parts
 * with Vercel AI SDK v6 and PostHog withTracing
 */

import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { PostHog } from 'posthog-node';
import { withTracing } from '@posthog/ai';
import { generateText, streamText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '..', '..', '.env') });
// Also try loading from parent if needed
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

// Enable debug mode to see PostHog events
posthog.debug(true);
console.log(`\n📊 PostHog Config: host=${process.env.POSTHOG_HOST}, key=${process.env.POSTHOG_API_KEY?.substring(0, 10)}...`);

const openaiClient = createOpenAI({
  apiKey: process.env.OPENAI_API_KEY!
});

const googleClient = createGoogleGenerativeAI({
  apiKey: process.env.GEMINI_API_KEY!
});

// Test image - 1x1 red pixel PNG
const testBase64Image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==';

interface TestCase {
  name: string;
  content: any[];
  provider?: 'openai' | 'google';
  streaming?: boolean;
}

const testCases: TestCase[] = [
  {
    name: "Test 1: Text only (should work)",
    content: [
      { type: 'text', text: 'What is in this image?' }
    ]
  },
  {
    name: "Test 2: Image type with data URL (existing working pattern)",
    content: [
      { type: 'text', text: 'What do you see?' },
      { type: 'image', image: `data:image/png;base64,${testBase64Image}` }
    ]
  },
  {
    name: "Test 3: File type with base64 string data",
    content: [
      { type: 'text', text: 'What do you see in this file?' },
      { type: 'file', data: testBase64Image, mediaType: 'image/png' }
    ]
  },
  {
    name: "Test 4: File type with data URL string",
    content: [
      { type: 'text', text: 'Describe this image.' },
      { type: 'file', data: `data:image/png;base64,${testBase64Image}`, mediaType: 'image/png' }
    ]
  },
  {
    name: "Test 5: File type with Uint8Array data",
    content: [
      { type: 'text', text: 'What is this?' },
      {
        type: 'file',
        data: new Uint8Array(Buffer.from(testBase64Image, 'base64')),
        mediaType: 'image/png'
      }
    ]
  },
  {
    name: "Test 6: File type with ArrayBuffer data",
    content: [
      { type: 'text', text: 'Describe the image.' },
      {
        type: 'file',
        data: Buffer.from(testBase64Image, 'base64').buffer,
        mediaType: 'image/png'
      }
    ]
  },
  {
    name: "Test 7: File type with Buffer data",
    content: [
      { type: 'text', text: 'What do you see?' },
      {
        type: 'file',
        data: Buffer.from(testBase64Image, 'base64'),
        mediaType: 'image/png'
      }
    ]
  },
  {
    name: "Test 8: File type with URL object",
    content: [
      { type: 'text', text: 'Describe this image from URL.' },
      {
        type: 'file',
        data: new URL('https://example.com/image.png'),
        mediaType: 'image/png'
      }
    ]
  },
  {
    name: "Test 9: File type with null data (potential bug)",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', data: null, mediaType: 'image/png' }
    ]
  },
  {
    name: "Test 10: File type with undefined data (potential bug)",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', data: undefined, mediaType: 'image/png' }
    ]
  },
  {
    name: "Test 11: File type with missing data property (potential bug)",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', mediaType: 'image/png' }
    ]
  },
  {
    name: "Test 12: File type with undefined mediaType",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', data: testBase64Image, mediaType: undefined }
    ]
  },
  {
    name: "Test 13: File type with missing mediaType",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', data: testBase64Image }
    ]
  },
  // Google/Gemini-specific tests
  {
    name: "Test 14: Gemini - File type with base64 string",
    content: [
      { type: 'text', text: 'What do you see in this file?' },
      { type: 'file', data: testBase64Image, mediaType: 'image/png' }
    ],
    provider: 'google'
  },
  {
    name: "Test 15: Gemini - File type with data URL",
    content: [
      { type: 'text', text: 'Describe this image.' },
      { type: 'file', data: `data:image/png;base64,${testBase64Image}`, mediaType: 'image/png' }
    ],
    provider: 'google'
  },
  {
    name: "Test 16: Gemini - File type with Uint8Array",
    content: [
      { type: 'text', text: 'What is this?' },
      {
        type: 'file',
        data: new Uint8Array(Buffer.from(testBase64Image, 'base64')),
        mediaType: 'image/png'
      }
    ],
    provider: 'google'
  },
  {
    name: "Test 17: Gemini - File type with Buffer",
    content: [
      { type: 'text', text: 'What do you see?' },
      {
        type: 'file',
        data: Buffer.from(testBase64Image, 'base64'),
        mediaType: 'image/png'
      }
    ],
    provider: 'google'
  },
  {
    name: "Test 18: Gemini - File type with null data",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', data: null, mediaType: 'image/png' }
    ],
    provider: 'google'
  },
  {
    name: "Test 19: Gemini - File type with undefined data",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', data: undefined, mediaType: 'image/png' }
    ],
    provider: 'google'
  },
  {
    name: "Test 20: Gemini - File type missing data property",
    content: [
      { type: 'text', text: 'What is this?' },
      { type: 'file', mediaType: 'image/png' }
    ],
    provider: 'google'
  },
  {
    name: "Test 21: Gemini - File type with ArrayBuffer",
    content: [
      { type: 'text', text: 'Describe this.' },
      {
        type: 'file',
        data: Buffer.from(testBase64Image, 'base64').buffer,
        mediaType: 'image/png'
      }
    ],
    provider: 'google'
  },
  // Streaming tests
  {
    name: "Test 22: Gemini Streaming - File type with base64",
    content: [
      { type: 'text', text: 'What do you see?' },
      { type: 'file', data: testBase64Image, mediaType: 'image/png' }
    ],
    provider: 'google',
    streaming: true
  },
  {
    name: "Test 23: Gemini Streaming - File type with Uint8Array",
    content: [
      { type: 'text', text: 'Describe this image.' },
      {
        type: 'file',
        data: new Uint8Array(Buffer.from(testBase64Image, 'base64')),
        mediaType: 'image/png'
      }
    ],
    provider: 'google',
    streaming: true
  },
  {
    name: "Test 24: Gemini Streaming - File type with Buffer",
    content: [
      { type: 'text', text: 'What is this?' },
      {
        type: 'file',
        data: Buffer.from(testBase64Image, 'base64'),
        mediaType: 'image/png'
      }
    ],
    provider: 'google',
    streaming: true
  }
];

async function runTest(testCase: TestCase): Promise<{ success: boolean; error?: string }> {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Running: ${testCase.name}`);
  console.log('='.repeat(60));

  try {
    // Select model based on provider
    const providerModel = testCase.provider === 'google'
      ? googleClient('gemini-2.5-flash')
      : openaiClient('gpt-4o-mini');

    const model = withTracing(providerModel, posthog, {
      posthogDistinctId: 'test-file-parts-user',
      posthogPrivacyMode: false,
      posthogProperties: {
        $ai_span_name: 'file_parts_test',
      },
    });

    const messages: any[] = [
      {
        role: 'user',
        content: testCase.content
      }
    ];

    console.log('\nMessage content structure:');
    console.log(JSON.stringify(testCase.content.map(c => ({
      type: c.type,
      hasData: 'data' in c,
      dataType: c.data === null ? 'null' : c.data === undefined ? 'undefined' : typeof c.data === 'object' ? c.data.constructor?.name : typeof c.data,
      mediaType: c.mediaType
    })), null, 2));

    const result = await generateText({
      model,
      messages,
      maxOutputTokens: 100
    });

    console.log(`\n✅ SUCCESS`);
    console.log(`Response: ${result.text.substring(0, 100)}...`);
    return { success: true };

  } catch (error: any) {
    console.log(`\n❌ FAILED`);
    console.log(`Error: ${error.message}`);
    if (error.stack) {
      console.log(`\nStack trace:`);
      console.log(error.stack);
    }
    return { success: false, error: error.message };
  }
}

async function main() {
  console.log('\n🧪 File Parts Error Reproduction Test');
  console.log('Testing various file part configurations with withTracing\n');

  const results: { name: string; success: boolean; error?: string }[] = [];

  // Ask which tests to run
  const args = process.argv.slice(2);
  let testsToRun = testCases;

  if (args.includes('--all')) {
    testsToRun = testCases;
  } else if (args.includes('--gemini')) {
    // Run only Gemini tests
    testsToRun = testCases.filter(t => t.provider === 'google');
  } else if (args.includes('--quick')) {
    // Run only tests likely to fail
    testsToRun = testCases.filter(t =>
      t.name.includes('null') ||
      t.name.includes('undefined') ||
      t.name.includes('missing') ||
      t.name.includes('Uint8Array') ||
      t.name.includes('ArrayBuffer') ||
      t.name.includes('Buffer')
    );
  } else if (args.length > 0 && !isNaN(parseInt(args[0]))) {
    // Run specific test by number
    const testNum = parseInt(args[0]);
    testsToRun = testCases.filter((_, i) => i + 1 === testNum);
  } else {
    // Default: run binary data tests (most likely to cause issues)
    console.log('Usage: npx ts-node test-file-parts.ts [--all|--quick|--gemini|<test-number>]');
    console.log('  --all: Run all tests');
    console.log('  --quick: Run tests likely to fail (null, undefined, binary)');
    console.log('  --gemini: Run only Gemini tests');
    console.log('  <number>: Run specific test (1-17)');
    console.log('\nDefaulting to --gemini mode...\n');
    testsToRun = testCases.filter(t => t.provider === 'google');
  }

  for (const testCase of testsToRun) {
    const result = await runTest(testCase);
    results.push({ name: testCase.name, ...result });
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('📊 SUMMARY');
  console.log('='.repeat(60));

  const passed = results.filter(r => r.success).length;
  const failed = results.filter(r => !r.success).length;

  console.log(`\nPassed: ${passed}/${results.length}`);
  console.log(`Failed: ${failed}/${results.length}`);

  if (failed > 0) {
    console.log('\n❌ Failed tests:');
    for (const result of results.filter(r => !r.success)) {
      console.log(`  - ${result.name}`);
      console.log(`    Error: ${result.error}`);
    }
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
