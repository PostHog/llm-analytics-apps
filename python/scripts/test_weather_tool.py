#!/usr/bin/env python3
"""
Test script for weather tool functionality.
Tests that providers correctly call the weather API with lat/lon/location_name.

Usage:
    python test_weather_tool.py                    # Run all tests
    python test_weather_tool.py --provider anthropic   # Test specific provider
    python test_weather_tool.py --list             # List available providers
"""

import os
import sys
import argparse

# Add parent directory to path so we can import from providers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from posthog import Posthog
from providers.anthropic import AnthropicProvider
from providers.anthropic_streaming import AnthropicStreamingProvider
from providers.gemini import GeminiProvider
from providers.gemini_streaming import GeminiStreamingProvider
from providers.openai import OpenAIProvider
from providers.openai_streaming import OpenAIStreamingProvider
from providers.openai_chat import OpenAIChatProvider
from providers.openai_chat_streaming import OpenAIChatStreamingProvider
from providers.langchain import LangChainProvider
from providers.litellm_provider import LiteLLMProvider
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define available providers
AVAILABLE_PROVIDERS = {
    'anthropic': (AnthropicProvider, "Anthropic Provider", False),
    'anthropic-streaming': (AnthropicStreamingProvider, "Anthropic Streaming Provider", True),
    'gemini': (GeminiProvider, "Google Gemini Provider", False),
    'gemini-streaming': (GeminiStreamingProvider, "Google Gemini Streaming Provider", True),
    'openai': (OpenAIProvider, "OpenAI Responses API Provider", False),
    'openai-streaming': (OpenAIStreamingProvider, "OpenAI Responses API Streaming Provider", True),
    'openai-chat': (OpenAIChatProvider, "OpenAI Chat Completions Provider", False),
    'openai-chat-streaming': (OpenAIChatStreamingProvider, "OpenAI Chat Completions Streaming Provider", True),
    'langchain': (LangChainProvider, "LangChain Provider", False),
    'litellm': (LiteLLMProvider, "LiteLLM Provider", False),
}

def init_posthog():
    """Initialize PostHog client"""
    posthog_api_key = os.getenv("POSTHOG_API_KEY")
    posthog_host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")

    if not posthog_api_key:
        print("⚠️  Warning: POSTHOG_API_KEY not set, analytics will not be tracked")
        return None

    return Posthog(
        project_api_key=posthog_api_key,
        host=posthog_host
    )

def test_provider(provider_class, provider_name, use_streaming=False):
    """Test a provider with weather tool calls"""
    print(f"\n{'='*80}")
    print(f"🧪 Testing {provider_name}")
    print(f"{'='*80}\n")

    # Initialize PostHog
    posthog_client = init_posthog()

    if not posthog_client:
        print("❌ Cannot run test without PostHog client")
        return False

    # Initialize provider
    provider = provider_class(posthog_client)

    # Test query
    test_query = "What's the weather in Dublin, Ireland?"
    print(f"📝 Query: {test_query}\n")

    try:
        if use_streaming:
            print("🔄 Streaming response:\n")
            full_response = ""
            for chunk in provider.chat_stream(test_query):
                print(chunk, end='', flush=True)
                full_response += chunk
            print("\n")
            response = full_response
        else:
            print("💬 Response:\n")
            response = provider.chat(test_query)
            print(response)
            print()

        # Check if response contains weather data
        if "°C" in response or "°F" in response:
            print("✅ Test PASSED - Weather data received!")

            # Check if location name is used
            if "Dublin" in response:
                print("✅ Location name displayed correctly!")
            else:
                print("⚠️  Warning: Location name might not be displayed")

            return True
        else:
            print("❌ Test FAILED - No weather data in response")
            return False

    except Exception as e:
        print(f"❌ Test FAILED with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Shutdown PostHog
        if posthog_client:
            posthog_client.shutdown()

def list_providers():
    """List all available providers"""
    print("\n" + "="*80)
    print("📋 Available Providers")
    print("="*80 + "\n")

    for key, (_, name, is_streaming) in AVAILABLE_PROVIDERS.items():
        stream_indicator = " (streaming)" if is_streaming else ""
        print(f"  • {key:25} - {name}{stream_indicator}")

    print()

def main():
    """Run tests based on CLI arguments"""
    parser = argparse.ArgumentParser(
        description="Test weather tool functionality across different AI providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_weather_tool.py                          # Run all tests
  python test_weather_tool.py --provider anthropic     # Test Anthropic only
  python test_weather_tool.py --provider openai-chat   # Test OpenAI Chat only
  python test_weather_tool.py --list                   # List available providers
        """
    )

    parser.add_argument(
        '--provider', '-p',
        choices=list(AVAILABLE_PROVIDERS.keys()),
        help='Test a specific provider'
    )

    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List available providers and exit'
    )

    args = parser.parse_args()

    # Handle --list flag
    if args.list:
        list_providers()
        sys.exit(0)

    print("\n" + "="*80)
    print("🚀 Weather Tool Test Suite")
    print("="*80)

    results = []

    # Determine which providers to test
    if args.provider:
        providers_to_test = {args.provider: AVAILABLE_PROVIDERS[args.provider]}
    else:
        providers_to_test = AVAILABLE_PROVIDERS

    # Run tests
    for key, (provider_class, provider_name, use_streaming) in providers_to_test.items():
        results.append((key, test_provider(provider_class, provider_name, use_streaming)))

    # Print summary
    print("\n" + "="*80)
    print("📊 Test Summary")
    print("="*80 + "\n")

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    # Exit with appropriate code
    sys.exit(0 if total_passed == total_tests else 1)

if __name__ == "__main__":
    main()
