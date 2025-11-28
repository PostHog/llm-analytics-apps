#!/usr/bin/env python3
"""
Test script for multi-language conversations with tool calls.
Creates a single conversation that switches between languages mid-conversation,
simulating a multilingual user.

Usage:
    python test_multi_language.py                    # Run multilingual conversation
    python test_multi_language.py --provider openai-chat  # Use specific provider
    python test_multi_language.py --list             # List available providers
"""

import os
import sys
import argparse

# Add parent directory to path so we can import from providers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from posthog import Posthog
from providers.openai_chat import OpenAIChatProvider
from providers.openai_chat_streaming import OpenAIChatStreamingProvider
from providers.anthropic import AnthropicProvider
from providers.anthropic_streaming import AnthropicStreamingProvider
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define available providers
AVAILABLE_PROVIDERS = {
    'openai-chat': (OpenAIChatProvider, "OpenAI Chat Completions Provider", False),
    'openai-chat-streaming': (OpenAIChatStreamingProvider, "OpenAI Chat Completions Streaming Provider", True),
    'anthropic': (AnthropicProvider, "Anthropic Provider", False),
    'anthropic-streaming': (AnthropicStreamingProvider, "Anthropic Streaming Provider", True),
}

# Multi-language conversation flow - starts in English, switches languages
MULTILINGUAL_CONVERSATION = [
    # Start in English
    {
        'language': 'English',
        'message': "Hello! I'm planning a trip to Europe and need some help with the weather. Can you check what the weather is like in London right now?",
        'expect_tool': 'get_weather',
    },
    {
        'language': 'English',
        'message': "Great, thanks! Also, tell me a joke to lighten the mood.",
        'expect_tool': 'tell_joke',
    },
    # Switch to Spanish
    {
        'language': 'Spanish',
        'message': "¡Perfecto! Ahora voy a continuar en español. ¿Cómo está el clima en Madrid?",
        'expect_tool': 'get_weather',
    },
    {
        'language': 'Spanish',
        'message': "¡Gracias! ¿Me puedes contar un chiste en español?",
        'expect_tool': 'tell_joke',
    },
    # Switch to German
    {
        'language': 'German',
        'message': "Jetzt spreche ich Deutsch. Wie ist das Wetter in Berlin?",
        'expect_tool': 'get_weather',
    },
    {
        'language': 'German',
        'message': "Danke schön! Erzähl mir bitte einen Witz auf Deutsch.",
        'expect_tool': 'tell_joke',
    },
    # Switch to French
    {
        'language': 'French',
        'message': "Maintenant je parle français. Quel temps fait-il à Paris?",
        'expect_tool': 'get_weather',
    },
    {
        'language': 'French',
        'message': "Merci beaucoup! Raconte-moi une blague en français, s'il te plaît.",
        'expect_tool': 'tell_joke',
    },
    # Back to English for wrap-up
    {
        'language': 'English',
        'message': "Thanks for all your help in multiple languages! You're a great multilingual assistant. One last weather check - how's it in Dublin, Ireland?",
        'expect_tool': 'get_weather',
    },
]


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


def run_multilingual_conversation(provider_class, provider_name, use_streaming=False):
    """Run a single conversation that switches between multiple languages"""
    print(f"\n{'='*80}")
    print(f"🌍 Multi-Language Conversation Test")
    print(f"📡 Provider: {provider_name}")
    print(f"{'='*80}\n")

    # Initialize PostHog
    posthog_client = init_posthog()

    if not posthog_client:
        print("❌ Cannot run test without PostHog client")
        return False

    # Initialize provider
    provider = provider_class(posthog_client)

    current_language = None
    success = True

    try:
        for i, turn in enumerate(MULTILINGUAL_CONVERSATION, 1):
            language = turn['language']
            message = turn['message']

            # Print language switch header if language changed
            if language != current_language:
                print(f"\n{'─'*60}")
                print(f"🗣️  Switching to {language}")
                print(f"{'─'*60}\n")
                current_language = language

            print(f"👤 User [{language}]: {message}\n")

            # Get response
            if use_streaming:
                print("🤖 Assistant: ", end='', flush=True)
                full_response = ""
                for chunk in provider.chat_stream(message):
                    print(chunk, end='', flush=True)
                    full_response += chunk
                print("\n")
                response = full_response
            else:
                response = provider.chat(message)
                print(f"🤖 Assistant: {response}\n")

        print(f"\n{'='*80}")
        print("✅ Multi-language conversation completed successfully!")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n❌ Error during conversation: {str(e)}")
        import traceback
        traceback.print_exc()
        success = False
    finally:
        # Shutdown PostHog
        if posthog_client:
            posthog_client.shutdown()

    return success


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
    """Run multi-language conversation test"""
    parser = argparse.ArgumentParser(
        description="Test multi-language conversations with AI providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_multi_language.py                          # Run with default provider
  python test_multi_language.py --provider openai-chat   # Use OpenAI Chat
  python test_multi_language.py --provider anthropic     # Use Anthropic
  python test_multi_language.py --list                   # List available providers
        """
    )

    parser.add_argument(
        '--provider', '-p',
        choices=list(AVAILABLE_PROVIDERS.keys()),
        default='openai-chat',
        help='Provider to use (default: openai-chat)'
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
    print("🚀 Multi-Language Conversation Test Suite")
    print("="*80)
    print("\nThis test simulates a user who switches between languages")
    print("during a single conversation: English → Spanish → German → French → English\n")

    # Get provider
    provider_class, provider_name, use_streaming = AVAILABLE_PROVIDERS[args.provider]

    # Run the test
    success = run_multilingual_conversation(provider_class, provider_name, use_streaming)

    # Print summary
    print("\n" + "="*80)
    print("📊 Test Summary")
    print("="*80 + "\n")

    if success:
        print("✅ PASS - Multi-language conversation completed")
    else:
        print("❌ FAIL - Conversation had errors")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
