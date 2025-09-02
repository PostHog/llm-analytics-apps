#!/usr/bin/env python3
"""
Unified AI Chatbot
Supports multiple LLM providers: Anthropic, Gemini, LangChain, and OpenAI
"""

import os
import platform
from dotenv import load_dotenv
from posthog import Posthog
from providers.anthropic import AnthropicProvider
from providers.anthropic_streaming import AnthropicStreamingProvider
from providers.gemini import GeminiProvider
from providers.gemini_streaming import GeminiStreamingProvider
from providers.langchain import LangChainProvider
from providers.litellm import LiteLLMProvider, LiteLLMStreamingProvider
from providers.openai import OpenAIProvider
from providers.openai_chat import OpenAIChatProvider
from providers.openai_chat_streaming import OpenAIChatStreamingProvider
from providers.openai_streaming import OpenAIStreamingProvider

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Initialize PostHog client (shared across all providers)
posthog = Posthog(
    os.getenv("POSTHOG_API_KEY"),
    host=os.getenv("POSTHOG_HOST", "https://app.posthog.com")
)

def clear_screen():
    """Clear the terminal screen"""
    if os.getenv('DEBUG') != '1':
        os.system('cls' if platform.system() == 'Windows' else 'clear')

def select_mode():
    """Select the operation mode"""
    modes = {
        "1": "Chat Mode",
        "2": "Tool Call Test",
        "3": "Message Test",
        "4": "Image Test",
        "5": "Embeddings Test"
    }
    
    print("\nSelect Mode:")
    print("=" * 50)
    for key, name in modes.items():
        if key == "1":
            print(f"  {key}. {name} (Interactive conversation)")
        elif key == "2":
            print(f"  {key}. {name} (Auto-test: Weather in Montreal)")
        elif key == "3":
            print(f"  {key}. {name} (Auto-test: Simple greeting)")
        elif key == "4":
            print(f"  {key}. {name} (Auto-test: Describe image)")
        elif key == "5":
            print(f"  {key}. {name} (Auto-test: Generate embeddings)")
    print("=" * 50)
    
    while True:
        try:
            choice = input("\nSelect a mode (1-5) or 'q' to quit: ").strip().lower()
            if choice in ["1", "2", "3", "4", "5"]:
                clear_screen()
                return choice
            elif choice == "q":
                print("\n👋 Goodbye!")
                exit(0)
            else:
                print("❌ Invalid choice. Please select 1, 2, 3, 4, or 5.")
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            exit(0)

def display_providers(mode=None):
    """Display available AI providers"""
    providers = {
        "1": "Anthropic",
        "2": "Anthropic Streaming",
        "3": "Google Gemini",
        "4": "Google Gemini Streaming",
        "5": "LangChain (OpenAI)",
        "6": "OpenAI Responses",
        "7": "OpenAI Responses Streaming",
        "8": "OpenAI Chat Completions",
        "9": "OpenAI Chat Completions Streaming",
        "10": "LiteLLM",
        "11": "LiteLLM Streaming"
    }
    
    # Filter providers for embeddings mode
    if mode == "5":
        # Only OpenAI providers support embeddings
        providers = {
            "6": "OpenAI Responses",
            "7": "OpenAI Responses Streaming",
            "8": "OpenAI Chat Completions",
            "9": "OpenAI Chat Completions Streaming"
        }
    
    print("\nAvailable AI Providers:")
    print("=" * 50)
    for key, name in providers.items():
        print(f"  {key}. {name}")
    print("=" * 50)
    
    return providers

def get_provider_choice(allow_mode_change=False, allow_all=False, valid_choices=None):
    """Get user's provider choice"""
    if valid_choices is None:
        valid_choices = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    
    # Build prompt based on valid choices
    if len(valid_choices) == 2:
        prompt = f"\nSelect a provider ({valid_choices[0]}-{valid_choices[1]})"
    elif len(valid_choices) == 3:
        prompt = f"\nSelect a provider ({valid_choices[0]}-{valid_choices[2]})"
    else:
        prompt = "\nSelect a provider (1-11)"
    
    if allow_all:
        prompt += ", 'a' for all providers"
    if allow_mode_change:
        prompt += ", or 'm' to change mode"
    prompt += ": "
    
    while True:
        try:
            choice = input(prompt).strip().lower()
            if choice in valid_choices:
                clear_screen()
                return choice
            elif allow_all and choice == "a":
                clear_screen()
                return "all"
            elif allow_mode_change and choice == "m":
                clear_screen()
                return "mode_change"
            else:
                print("❌ Invalid choice. Please select a valid option.")
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            exit(0)


def create_provider(choice):
    """Create the selected provider instance"""
    if choice == "1":
        return AnthropicProvider(posthog)
    elif choice == "2":
        return AnthropicStreamingProvider(posthog)
    elif choice == "3":
        return GeminiProvider(posthog)
    elif choice == "4":
        return GeminiStreamingProvider(posthog)
    elif choice == "5":
        return LangChainProvider(posthog)
    elif choice == "6":
        return OpenAIProvider(posthog)
    elif choice == "7":
        return OpenAIStreamingProvider(posthog)
    elif choice == "8":
        return OpenAIChatProvider(posthog)
    elif choice == "9":
        return OpenAIChatStreamingProvider(posthog)
    elif choice == "10":
        return LiteLLMProvider(posthog, "openai")
    elif choice == "11":
        return LiteLLMStreamingProvider(posthog, "openai")

def run_chat(provider):
    """Run the chat loop with the selected provider"""
    print(f'\n🤖 Welcome to the chatbot using {provider.get_name()}!')
    print("🌤️ All providers have weather tools - just ask about weather in any city!")
    
    # Show additional info for LangChain if available
    if hasattr(provider, 'get_description'):
        print(provider.get_description())
    
    print("Type your messages below. Type 'q' to return to provider selection.\n")
    
    while True:
        try:
            user_input = input('👤 You: ').strip()
            
            if not user_input:
                continue
            
            # Check for quit command to return to provider selection
            if user_input.lower() == 'q':
                print('\n↩️  Returning to provider selection...\n')
                return True
            
            # Check if provider supports streaming
            if hasattr(provider, 'chat_stream') and callable(getattr(provider, 'chat_stream')):
                # Stream the response
                import sys
                print('\n🤖 Bot: ', end='', flush=True)
                for chunk in provider.chat_stream(user_input):
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                print()  # New line after streaming completes
            else:
                # Get response from the provider
                response = provider.chat(user_input)
                print(f'\n🤖 Bot: {response}')
            
            print('─' * 50)
            
        except KeyboardInterrupt:
            print('\n\n👋 Goodbye!')
            exit(0)
        except Exception as error:
            print(f'❌ Error: {str(error)}')
            print('─' * 50)

def run_tool_call_test(provider):
    """Run automated tool call test with weather query"""
    test_query = "What is the weather in Montreal, Canada?"
    
    print(f'\nTool Call Test: {provider.get_name()}')
    print('-' * 50)
    print(f'Query: "{test_query}"')
    print()
    
    try:
        # Reset conversation for clean test
        provider.reset_conversation()
        
        # Send the test query
        response = provider.chat(test_query)
        
        print(f'Response: {response}')
        print()
        return True, None
        
    except Exception as error:
        print(f'❌ Error: {str(error)}')
        return False, str(error)

def run_message_test(provider):
    """Run automated message test with simple greeting"""
    test_query = "Hi, how are you today?"
    
    print(f'\nMessage Test: {provider.get_name()}')
    print('-' * 50)
    print(f'Query: "{test_query}"')
    print()
    
    try:
        # Reset conversation for clean test
        provider.reset_conversation()
        
        # Send the test query
        response = provider.chat(test_query)
        
        print(f'Response: {response}')
        print()
        return True, None
        
    except Exception as error:
        print(f'❌ Error: {str(error)}')
        return False, str(error)

def run_image_test(provider):
    """Run automated image test with sample image"""
    base64_image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='
    test_query = 'What do you see in this image? Please describe it.'
    
    print(f'\nImage Test: {provider.get_name()}')
    print('-' * 50)
    print(f'Query: "{test_query}"')
    print(f'Image: 1x1 red pixel (base64 encoded)')
    print()
    
    try:
        # Reset conversation for clean test
        provider.reset_conversation()
        
        # Send the test query with image
        response = provider.chat(test_query, base64_image)
        
        print(f'Response: {response}')
        print()
        return True, None
        
    except Exception as error:
        print(f'❌ Error: {str(error)}')
        return False, str(error)

def run_embeddings_test(provider):
    """Run automated embeddings test"""
    test_texts = [
        "The quick brown fox jumps over the lazy dog."
    ]
    
    print(f'\nEmbeddings Test: {provider.get_name()}')
    print('-' * 50)
    
    # Check if provider supports embeddings
    if not hasattr(provider, 'embed'):
        print(f'❌ {provider.get_name()} does not support embeddings')
        return False, "Provider does not support embeddings"
    
    try:
        for i, text in enumerate(test_texts, 1):
            print(f'\nTest {i}: "{text}"')
            
            # Generate embeddings
            embedding = provider.embed(text)
            
            if embedding:
                print(f'✅ Generated embedding with {len(embedding)} dimensions')
                # Show first 5 values as sample
                print(f'   Sample values: {embedding[:5]}...')
            else:
                print(f'❌ Failed to generate embedding')
                return False, f"Failed to generate embedding for text {i}"
        
        print()
        return True, None
        
    except Exception as error:
        print(f'❌ Error: {str(error)}')
        return False, str(error)

def run_all_tests(mode):
    """Run tests on all providers and show summary"""
    providers_info = [
        ("1", "Anthropic"),
        ("2", "Anthropic Streaming"),
        ("3", "Google Gemini"),
        ("4", "Google Gemini Streaming"),
        ("5", "LangChain (OpenAI)"),
        ("6", "OpenAI Responses"),
        ("7", "OpenAI Responses Streaming"),
        ("8", "OpenAI Chat Completions"),
        ("9", "OpenAI Chat Completions Streaming"),
        ("10", "LiteLLM"),
        ("11", "LiteLLM Streaming")
    ]
    
    # Filter providers for embeddings test (only those that support it)
    if mode == "5":
        # Only OpenAI providers support embeddings
        providers_info = [
            ("6", "OpenAI Responses"),
            ("7", "OpenAI Responses Streaming"),
            ("8", "OpenAI Chat Completions"),
            ("9", "OpenAI Chat Completions Streaming")
        ]
    
    if mode == "2":
        test_name = "Tool Call Test"
    elif mode == "3":
        test_name = "Message Test"
    elif mode == "4":
        test_name = "Image Test"
    elif mode == "5":
        test_name = "Embeddings Test"
    else:
        test_name = "Unknown Test"
    
    print(f"\n🔄 Running {test_name} on all providers...")
    print("=" * 60)
    print()
    
    results = []
    
    for provider_id, provider_name in providers_info:
        print(f"[{provider_id}/11] Testing {provider_name}...")
        
        try:
            provider = create_provider(provider_id)
            
            # Run the appropriate test
            if mode == "2":
                success, error = run_tool_call_test(provider)
            elif mode == "3":
                success, error = run_message_test(provider)
            elif mode == "4":
                success, error = run_image_test(provider)
            elif mode == "5":
                success, error = run_embeddings_test(provider)
            else:
                success, error = False, "Unknown test mode"
            
            results.append({
                "name": provider_name,
                "success": success,
                "error": error
            })
            
        except Exception as init_error:
            print(f"   ❌ Failed to initialize: {str(init_error)}")
            results.append({
                "name": provider_name,
                "success": False,
                "error": f"Initialization failed: {str(init_error)}"
            })
    
    # Print summary
    print("\n" + "=" * 60)
    print(f"📊 {test_name} Summary")
    print("=" * 60)
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    for result in successful:
        print(f"   • {result['name']}")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(results)}")
        for result in failed:
            print(f"   • {result['name']}")
            print(f"     Error: {result['error']}")
    
    print("=" * 60)
    print()

def main():
    """Main application entry point"""
    clear_screen()
    print("\n🚀 Unified AI Chatbot")
    print("Choose your mode and AI provider")
    print()
    
    # First, select the mode
    mode = select_mode()
    
    # Main loop for provider selection and testing
    while True:
        # Display providers and get user choice
        providers = display_providers(mode)
        
        # Allow mode change for all modes, 'all' option only for test modes
        allow_mode_change = (mode in ["1", "2", "3", "4", "5"])
        allow_all = (mode in ["2", "3", "4", "5"])
        valid_choices = list(providers.keys())
        choice = get_provider_choice(allow_mode_change=allow_mode_change, allow_all=allow_all, valid_choices=valid_choices)
        
        # Check if user wants to change mode
        if choice == "mode_change":
            mode = select_mode()
            continue
        
        # Check if user wants to test all providers
        if choice == "all":
            run_all_tests(mode)
            continue
        
        # Create provider instance
        try:
            provider = create_provider(choice)
            print(f"\n✅ Initialized {provider.get_name()}")
        except Exception as error:
            print(f"❌ Failed to initialize provider: {str(error)}")
            continue
        
        # Execute based on mode
        if mode == "1":
            # Chat Mode - run interactive chat and continue when done
            run_chat(provider)
            continue
        elif mode == "2":
            # Tool Call Test - run test and loop back
            success, error = run_tool_call_test(provider)
            if not error:
                print()
        elif mode == "3":
            # Message Test - run test and loop back
            success, error = run_message_test(provider)
            if not error:
                print()
        elif mode == "4":
            # Image Test - run test and loop back
            success, error = run_image_test(provider)
            if not error:
                print()
        elif mode == "5":
            # Embeddings Test - run test and loop back
            success, error = run_embeddings_test(provider)
            if not error:
                print()

if __name__ == "__main__":
    main()