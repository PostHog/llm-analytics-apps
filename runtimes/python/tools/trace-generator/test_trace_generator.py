#!/usr/bin/env python3
"""
Test script for the trace generator functionality
"""

import os
import sys
from dotenv import load_dotenv
from posthog import Posthog

# Add current directory to path so we can import trace_generator
sys.path.insert(0, os.path.dirname(__file__))
from trace_generator import TraceBuilder, EventGenerator

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def test_event_generation():
    """Test that event generation works correctly"""
    print("🧪 Testing Event Generation...")

    # Test trace ID generation
    trace_id = EventGenerator.generate_trace_id()
    print(f"✅ Generated trace ID: {trace_id}")

    # Test trace event generation
    trace_event = EventGenerator.generate_trace_event(trace_id, "test_trace")
    print(f"✅ Generated trace event: {trace_event['event']}")

    # Test span event generation
    span_event = EventGenerator.generate_span_event(trace_id, "test_span")
    print(f"✅ Generated span event: {span_event['event']}")

    # Test generation event generation
    gen_event = EventGenerator.generate_generation_event(trace_id)
    print(f"✅ Generated generation event: {gen_event['event']}")

    # Test embedding event generation
    embed_event = EventGenerator.generate_embedding_event(trace_id)
    print(f"✅ Generated embedding event: {embed_event['event']}")

    print("✅ All event generation tests passed!")
    return True

def test_trace_building():
    """Test that trace building works correctly"""
    print("\n🏗️ Testing Trace Building...")

    # Initialize PostHog client (but don't send)
    posthog = Posthog(
        os.getenv("POSTHOG_API_KEY"),
        host=os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    )

    builder = TraceBuilder(posthog)

    # Test simple chat trace
    result = builder.build_simple_chat_trace()
    print(f"✅ Simple chat trace: {result['events_count']} events")

    # Test RAG pipeline trace
    result = builder.build_rag_pipeline_trace()
    print(f"✅ RAG pipeline trace: {result['events_count']} events")

    # Test multi-agent trace
    result = builder.build_multiagent_trace()
    print(f"✅ Multi-agent trace: {result['events_count']} events")

    # Test custom trace with new structure
    custom_structure = {
        "name": "test_custom",
        "nodes": [
            {"type": "span", "name": "data_retrieval"},
            {"type": "embedding", "name": "query_embedding", "parent": "data_retrieval", "model": "text-embedding-3-small"},
            {"type": "generation", "name": "initial_response", "purpose": "planning", "model": "gpt-4o"},
            {"type": "span", "name": "processing", "parent": "data_retrieval"},
            {"type": "generation", "name": "final_response", "parent": "processing", "purpose": "synthesis", "model": "gpt-4o-mini"}
        ]
    }
    result = builder.build_custom_trace(custom_structure)
    print(f"✅ Custom trace: {result['events_count']} events")

    # Test event summary
    summary = builder.get_event_summary()
    print(f"✅ Event summary: {summary}")

    print("✅ All trace building tests passed!")
    return True

def test_validation():
    """Test environment validation"""
    print("\n🔍 Testing Validation...")

    # Test that we have required environment variables
    api_key = os.getenv("POSTHOG_API_KEY")
    if api_key:
        print(f"✅ PostHog API key found (length: {len(api_key)})")
    else:
        print("⚠️  No PostHog API key found - this is expected in test environment")

    host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    print(f"✅ PostHog host: {host}")

    print("✅ Validation tests completed!")
    return True

def main():
    """Run all tests"""
    print("🎯 Testing LLM Trace Generator")
    print("=" * 50)

    try:
        # Run tests
        test_event_generation()
        test_trace_building()
        test_validation()

        print("\n🎉 All tests passed successfully!")
        print("\n💡 The trace generator is ready to use interactively!")
        print("   Run: python trace_generator.py")

    except Exception as error:
        print(f"\n❌ Test failed: {str(error)}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)