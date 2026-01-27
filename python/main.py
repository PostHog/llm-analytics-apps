#!/usr/bin/env python3
"""
Unified AI Chatbot
Supports multiple LLM providers: Anthropic, Gemini, LangChain, and OpenAI
"""

import os
import platform
import uuid
from dotenv import load_dotenv
from posthog import Posthog
from providers.anthropic import AnthropicProvider
from providers.anthropic_streaming import AnthropicStreamingProvider
from providers.gemini import GeminiProvider
from providers.gemini_streaming import GeminiStreamingProvider
from providers.langchain import LangChainProvider
from providers.openai import OpenAIProvider
from providers.openai_chat import OpenAIChatProvider
from providers.openai_chat_streaming import OpenAIChatStreamingProvider
from providers.openai_streaming import OpenAIStreamingProvider
from providers.litellm_provider import LiteLLMProvider
from providers.litellm_streaming import LiteLLMStreamingProvider
from providers.openai_otel import OpenAIOtelProvider
from providers.openai_transcription import OpenAITranscriptionProvider
from openai_agents.runner import OpenAIAgentsRunner

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Show debug mode status if enabled
if os.getenv('DEBUG') == '1':
    print("\n" + "=" * 80)
    print("🐛 DEBUG MODE ENABLED")
    print("=" * 80 + "\n")

# Generate session ID for grouping traces (if enabled)
def should_enable_session_id():
    """Check if session ID should be enabled based on env var"""
    value = os.getenv("ENABLE_AI_SESSION_ID", "True")
    return value.lower() in ("true", "1", "yes")

ai_session_id = str(uuid.uuid4()) if should_enable_session_id() else None

# Initialize PostHog client with super_properties for session ID
super_properties = {"$ai_session_id": ai_session_id} if ai_session_id else None

posthog = Posthog(
    os.getenv("POSTHOG_API_KEY"),
    host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
    super_properties=super_properties
)

if ai_session_id:
    print(f"\n🔗 AI Session ID enabled: {ai_session_id}")
    print("All traces in this session will be grouped together.\n")

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
        "5": "Embeddings Test",
        "6": "Transcription Test"
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
        elif key == "6":
            print(f"  {key}. {name} (Auto-test: Transcribe audio)")
    print("=" * 50)

    while True:
        try:
            choice = input("\nSelect a mode (1-6) or 'q' to quit: ").strip().lower()
            if choice in ["1", "2", "3", "4", "5", "6"]:
                clear_screen()
                return choice
            elif choice == "q":
                print("\n👋 Goodbye!")
                exit(0)
            else:
                print("❌ Invalid choice. Please select 1, 2, 3, 4, 5, or 6.")
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
        "10": "LiteLLM (Sync)",
        "11": "LiteLLM (Async)",
        "12": "OpenAI with OpenTelemetry",
        "13": "OpenAI Transcriptions with Whisper",
        "14": "OpenAI Agents SDK"
    }

    # Filter providers for embeddings mode
    if mode == "5":
        # Only OpenAI providers and LiteLLM support embeddings
        providers = {
            "6": "OpenAI Responses",
            "7": "OpenAI Responses Streaming",
            "8": "OpenAI Chat Completions",
            "9": "OpenAI Chat Completions Streaming",
            "10": "LiteLLM (Sync)",
            "11": "LiteLLM (Async)"
        }

    # Filter providers for transcription mode
    if mode == "6":
        # Only OpenAI Transcription provider supports audio transcription
        providers = {
            "13": "OpenAI Transcriptions - Whisper"
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
        valid_choices = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]
    
    # Build prompt based on valid choices
    if len(valid_choices) == 1:
        prompt = f"\nSelect a provider ({valid_choices[0]})"
    elif len(valid_choices) == 2:
        prompt = f"\nSelect a provider ({valid_choices[0]}-{valid_choices[1]})"
    elif len(valid_choices) == 3:
        prompt = f"\nSelect a provider ({valid_choices[0]}-{valid_choices[2]})"
    else:
        prompt = "\nSelect a provider (1-13)"
    
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

def prompt_thinking_config():
    """Ask user if they want extended thinking enabled for Anthropic"""
    print("\n🧠 Extended Thinking Configuration")
    print("=" * 50)
    print("Extended thinking shows Claude's reasoning process.")
    print("This can improve response quality for complex problems.")
    print("=" * 50)
    
    while True:
        try:
            choice = input("\nEnable extended thinking? (y/n) [default: n]: ").strip().lower()
            if choice in ["y", "yes"]:
                # Ask for budget (optional)
                budget_input = input("Thinking budget tokens (1024-32000) [default: 10000]: ").strip()
                if budget_input:
                    try:
                        budget = int(budget_input)
                        budget = max(1024, min(budget, 32000))  # Clamp between 1024 and 32000
                        return True, budget
                    except ValueError:
                        print("⚠️  Invalid number, using default (10000)")
                        return True, 10000
                return True, 10000
            elif choice in ["n", "no", ""]:
                return False, None
            else:
                print("❌ Please enter 'y' or 'n'")
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            exit(0)

def create_provider(choice, enable_thinking=False, thinking_budget=None):
    """Create the selected provider instance"""
    if choice == "1":
        return AnthropicProvider(posthog, enable_thinking, thinking_budget)
    elif choice == "2":
        return AnthropicStreamingProvider(posthog, enable_thinking, thinking_budget)
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
        return LiteLLMProvider(posthog)
    elif choice == "11":
        return LiteLLMStreamingProvider(posthog)
    elif choice == "12":
        return OpenAIOtelProvider(posthog)
    elif choice == "13":
        return OpenAITranscriptionProvider(posthog)
    elif choice == "14":
        return OpenAIAgentsRunner(posthog)

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
    print('Image: 1x1 red pixel (base64 encoded)')
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
                print('❌ Failed to generate embedding')
                return False, f"Failed to generate embedding for text {i}"
        
        print()
        return True, None
        
    except Exception as error:
        print(f'❌ Error: {str(error)}')
        return False, str(error)


def run_transcription_test(provider):
    """Run automated transcription test with audio file"""
    print(f'\nTranscription Test: {provider.get_name()}')
    print('-' * 50)

    # Check if provider supports transcription
    if not hasattr(provider, 'transcribe') or not callable(getattr(provider, 'transcribe')):
        print(f'❌ {provider.get_name()} does not support transcription')
        return False, "Provider does not support transcription"

    # Check for test audio file (in the root of llm-analytics-apps)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    audio_path = os.path.join(script_dir, '..', 'test-audio.mp3')

    if not os.path.exists(audio_path):
        print(f'❌ Test audio file not found at: {audio_path}')
        print('Please create a test audio file (test-audio.mp3) in the llm-analytics-apps directory')
        print('You can use any short audio file (mp3, wav, m4a, etc.)')
        return False, "Test audio file not found"

    try:
        print(f'\nTranscribing audio file: {audio_path}')
        print()

        # Transcribe the audio
        transcription = provider.transcribe(audio_path)

        if transcription and len(transcription) > 0:
            print('✅ Transcription successful')
            print('\nTranscription text:')
            print(f'"{transcription}"')
            print()
        else:
            print('❌ Failed to transcribe audio')
            return False, "Failed to generate transcription"

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
        ("10", "LiteLLM (Sync)"),
        ("11", "LiteLLM (Async)"),
        ("13", "OpenAI Agents SDK")
    ]

    # Filter providers for embeddings test (only those that support it)
    if mode == "5":
        # Only OpenAI providers and LiteLLM support embeddings
        providers_info = [
            ("6", "OpenAI Responses"),
            ("7", "OpenAI Responses Streaming"),
            ("8", "OpenAI Chat Completions"),
            ("9", "OpenAI Chat Completions Streaming"),
            ("10", "LiteLLM (Sync)"),
            ("11", "LiteLLM (Async)")
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
        print(f"[{provider_id}/{len(providers_info)}] Testing {provider_name}...")
        
        try:
            # For automated tests, don't enable thinking by default
            provider = create_provider(provider_id, False, None)
            
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
        
        # Allow mode change for all modes, 'all' option only for test modes (not transcription - only 1 provider)
        allow_mode_change = (mode in ["1", "2", "3", "4", "5", "6"])
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
        
        # Check if Anthropic provider selected and prompt for thinking config
        enable_thinking = False
        thinking_budget = None
        if choice in ["1", "2"]:  # Anthropic providers
            enable_thinking, thinking_budget = prompt_thinking_config()
        
        # Create provider instance
        try:
            provider = create_provider(choice, enable_thinking, thinking_budget)
            status_msg = f"\n✅ Initialized {provider.get_name()}"
            if enable_thinking:
                status_msg += f" (Thinking: enabled, budget: {thinking_budget})"
            print(status_msg)

            # Show mode selection for OpenAI Agents SDK
            if choice == "13" and hasattr(provider, 'prompt_mode_selection'):
                provider.prompt_mode_selection()
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
        elif mode == "6":
            # Transcription Test - run test and loop back
            success, error = run_transcription_test(provider)
            if not error:
                print()


if __name__ == "__main__":
    main()
