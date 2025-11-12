#!/usr/bin/env node

// Quick test to verify PostHog ingestion is working
import { PostHog } from 'posthog-node';

const posthog = new PostHog(
  'phc_ABOAagCSNfMOUWin6A6Tda0WuhzWLFSXjSgSiq9KKBs',
  {
    host: 'https://us.i.posthog.com',
    flushAt: 1,
    flushInterval: 0
  }
);

console.log('🧪 Sending test events to PostHog...\n');

// Send a simple test event
posthog.capture({
  distinctId: 'test-user-' + Date.now(),
  event: 'test_event_simple',
  properties: {
    test_type: 'ingestion_test',
    timestamp: new Date().toISOString(),
    message: 'Simple test event'
  }
});
console.log('✅ Sent: test_event_simple');

// Send an LLM-like event to mimic what the transcription would send
posthog.capture({
  distinctId: 'test-user-' + Date.now(),
  event: 'llm_event',
  properties: {
    $lib: '@posthog/ai',
    $lib_version: '6.4.4',
    model: 'whisper-1',
    provider: 'openai',
    input: 'test audio transcription',
    output: 'This is a test transcription output',
    latency: 1.23,
    usage: {
      inputTokens: 0,
      outputTokens: 50
    },
    test_type: 'llm_ingestion_test',
    timestamp: new Date().toISOString()
  }
});
console.log('✅ Sent: llm_event');

// Send a third event to verify multiple events work
posthog.capture({
  distinctId: 'test-user-' + Date.now(),
  event: 'test_event_with_metadata',
  properties: {
    test_type: 'ingestion_test',
    timestamp: new Date().toISOString(),
    metadata: {
      key1: 'value1',
      key2: 'value2',
      nested: {
        deep: 'data'
      }
    }
  }
});
console.log('✅ Sent: test_event_with_metadata');

console.log('\n⏳ Flushing events and shutting down...');

await posthog.shutdown();

console.log('✅ All events sent successfully!');
console.log('\n📊 Check your PostHog dashboard at: https://us.posthog.com');
console.log('   Look for events from distinct IDs starting with "test-user-"');
