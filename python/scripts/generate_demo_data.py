#!/usr/bin/env python3
"""
Demo Data Generator for PostHog LLM Analytics

Generates realistic chat data by using a LangChain-powered "User Simulator" agent
that has actual conversations with various LLM providers.

The User Simulator acts as a curious human user, picking random topics and having
natural multi-turn conversations with the target providers.
"""

import argparse
import os
import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from dotenv import load_dotenv

# Add parent directory to path so we can import providers
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from posthog import Posthog

# Provider imports
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


# Topics the user simulator can choose from
TOPICS = [
    # Weather & Environment
    "weather in various cities around the world",
    "climate patterns and seasonal changes",
    "extreme weather events and how to prepare",

    # Programming & Tech
    "how to write code in Python",
    "helping debug a programming problem",
    "understanding how technology works",
    "learning about APIs and how to use them",
    "best practices for writing clean code",
    "how databases work and when to use them",
    "getting started with machine learning",
    "web development tips and frameworks",
    "mobile app development basics",
    "DevOps and deployment strategies",
    "cybersecurity basics and staying safe online",

    # Food & Cooking
    "how to cook a specific dish",
    "meal planning and nutrition advice",
    "baking tips and dessert recipes",
    "cooking techniques for beginners",
    "international cuisines and their specialties",
    "dietary restrictions and alternative ingredients",

    # Science & Education
    "explaining a scientific concept",
    "learning about history",
    "understanding economics and finance basics",
    "exploring philosophy and ethics",
    "learning about astronomy and space",
    "biology and how the human body works",
    "chemistry in everyday life",
    "physics concepts made simple",
    "environmental science and sustainability",

    # Entertainment & Culture
    "recommending books or movies",
    "asking for jokes or humor",
    "discussing music and artists",
    "video games and gaming culture",
    "TV shows worth watching",
    "podcasts and audiobook recommendations",
    "art and creative expression",

    # Travel & Lifestyle
    "discussing travel destinations",
    "planning a vacation itinerary",
    "budget travel tips and tricks",
    "local attractions and hidden gems",
    "cultural etiquette when traveling abroad",

    # Productivity & Career
    "getting advice on productivity",
    "career advice and job searching",
    "learning a new skill",
    "time management strategies",
    "work-life balance tips",
    "negotiation and communication skills",
    "leadership and team management",
    "starting a business or side project",

    # Health & Wellness
    "asking about health and fitness",
    "mental health and stress management",
    "sleep hygiene and better rest",
    "meditation and mindfulness practices",
    "workout routines for different goals",

    # Writing & Communication
    "getting help with writing",
    "improving grammar and style",
    "public speaking tips",
    "email etiquette and professional communication",
    "storytelling techniques",
    "learning a new language",

    # Home & DIY
    "home improvement and DIY projects",
    "gardening tips and plant care",
    "organizing and decluttering",
    "interior design ideas",
    "basic car maintenance",

    # Finance & Legal
    "personal finance and budgeting",
    "investing basics for beginners",
    "understanding taxes and deductions",
    "retirement planning",
    "understanding contracts and agreements",

    # Relationships & Social
    "relationship advice and communication",
    "parenting tips and child development",
    "making new friends as an adult",
    "dealing with difficult people",
    "gift ideas for different occasions",

    # Miscellaneous
    "fun facts and trivia",
    "brain teasers and riddles",
    "explaining pop culture references",
    "pet care and animal behavior",
    "photography tips for beginners",
    "crafts and hobbies to try",

    # Frustrated & Negative scenarios
    "complaining about a product that keeps breaking",
    "dealing with a billing error that won't get resolved",
    "ranting about terrible customer service experiences",
    "frustrated with software that lost their work",
    "angry about misleading advertising",
    "upset about a cancelled flight and ruined travel plans",
    "complaining about noisy neighbors and landlord issues",
    "furious about a data breach affecting their account",
    "venting about a bad restaurant experience",
    "annoyed by repeated spam calls and scam attempts",
    "arguing that a previous AI answer was completely wrong",
    "demanding a refund for a defective product",
]

# User personas the simulator can adopt
USER_PERSONAS = [
    # Learning styles
    "a curious beginner who asks simple follow-up questions",
    "an enthusiastic learner who loves to dig deeper into topics",
    "a visual learner who asks for examples and analogies",
    "someone who learns by doing and wants step-by-step instructions",

    # Professional personas
    "an experienced developer looking for specific technical details",
    "a busy professional who wants quick, concise answers",
    "a manager trying to understand technical concepts at a high level",
    "a freelancer looking for practical tips to improve their work",
    "a startup founder exploring new ideas",
    "a teacher preparing lesson materials",

    # Student personas
    "a student working on a homework assignment",
    "a graduate student doing research",
    "someone preparing for a job interview",
    "a self-taught learner filling knowledge gaps",

    # Personality types
    "someone who's a bit skeptical and asks clarifying questions",
    "a friendly conversationalist who enjoys chatting",
    "an impatient person who wants direct answers without fluff",
    "a detail-oriented person who wants comprehensive information",
    "someone who likes to play devil's advocate",
    "a humorous person who appreciates wit and wordplay",

    # Situational personas
    "someone planning a trip and needing recommendations",
    "a parent trying to explain something to their child",
    "someone dealing with a problem and looking for solutions",
    "a hobbyist exploring a new interest",
    "someone comparing options before making a decision",
    "a person who just wants to have a casual conversation",

    # Communication styles
    "someone who asks lots of follow-up questions",
    "a person who likes to summarize and confirm understanding",
    "someone who shares personal anecdotes while chatting",
    "a minimalist communicator who uses short messages",
    "someone who thinks out loud and refines their questions",

    # Specific needs
    "someone with accessibility needs looking for inclusive solutions",
    "a non-native English speaker who appreciates clear explanations",
    "an expert fact-checking information they already know",
    "someone procrastinating who went down a rabbit hole",
    "a night owl having a late-night curiosity session",

    # Frustrated & Angry personas
    "an extremely frustrated customer who has been passed around to 5 different support agents",
    "someone who is furious and uses lots of caps and exclamation marks",
    "a sarcastic person who mocks every response they get",
    "someone who keeps saying the AI is useless and demands to speak to a human",
    "an angry user who threatens to switch to a competitor",
    "a passive-aggressive person who says 'fine I guess' to every suggestion",
    "someone having an absolutely terrible day who takes it out on the chat",
    "a person who insists the AI gave them wrong information last time and wants it fixed NOW",
]

# Available providers
PROVIDERS = {
    "anthropic": ("Anthropic", AnthropicProvider),
    "anthropic_streaming": ("Anthropic Streaming", AnthropicStreamingProvider),
    "gemini": ("Google Gemini", GeminiProvider),
    "gemini_streaming": ("Google Gemini Streaming", GeminiStreamingProvider),
    "langchain": ("LangChain (OpenAI)", LangChainProvider),
    "openai": ("OpenAI Responses", OpenAIProvider),
    "openai_streaming": ("OpenAI Responses Streaming", OpenAIStreamingProvider),
    "openai_chat": ("OpenAI Chat Completions", OpenAIChatProvider),
    "openai_chat_streaming": ("OpenAI Chat Completions Streaming", OpenAIChatStreamingProvider),
    "litellm": ("LiteLLM (Sync)", LiteLLMProvider),
    "litellm_streaming": ("LiteLLM (Async)", LiteLLMStreamingProvider),
}


class UserSimulator:
    """
    A LangChain-powered agent that simulates a human user having conversations.

    It generates realistic user messages based on:
    - A randomly selected topic
    - A randomly selected persona
    - The conversation history so far
    """

    def __init__(self, topic: str, persona: str, max_turns: int):
        self.topic = topic
        self.persona = persona
        self.max_turns = max_turns
        self.current_turn = 0

        # Use a lightweight model for user simulation
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.8,  # Higher temperature for more varied user messages
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        self.system_prompt = f"""You are simulating a human user having a conversation with an AI assistant.

Your persona: {persona}

The topic you're interested in: {topic}

Your job is to generate realistic user messages as if you were actually chatting with an AI assistant.

Rules:
1. Start with an opening message related to your topic
2. Ask follow-up questions based on the assistant's responses
3. Be natural - sometimes agree, sometimes ask for clarification, sometimes change direction slightly
4. Keep messages relatively short (1-3 sentences typically)
5. After a few turns, you may naturally wrap up the conversation with thanks or a closing remark
6. Don't be overly formal or robotic - be conversational

You will receive the conversation history and should generate ONLY the next user message.
Do not include any prefix like "User:" - just output the message content directly."""

        self.messages = [SystemMessage(content=self.system_prompt)]

    def generate_message(self, assistant_response: Optional[str] = None) -> tuple[str, bool]:
        """
        Generate the next user message based on conversation history.

        Returns:
            tuple: (message, should_end) where should_end indicates if this should be the last turn
        """
        self.current_turn += 1

        # Add assistant's response to our history if provided
        if assistant_response:
            self.messages.append(AIMessage(content=f"[Assistant's response]: {assistant_response}"))

        # Add instruction for this turn
        if self.current_turn == 1:
            instruction = "Generate your opening message to start the conversation about your topic."
        elif self.current_turn >= self.max_turns:
            instruction = "This is your final turn. Generate a brief closing message (like thanking the assistant or saying goodbye)."
        else:
            # Occasionally prompt for natural conversation endings
            if self.current_turn >= 3 and random.random() < 0.3:
                instruction = "Based on the conversation so far, generate your next message. You may choose to wrap up naturally if you feel satisfied, or continue if you want to know more."
            else:
                instruction = "Based on the assistant's response, generate your next natural follow-up message."

        self.messages.append(HumanMessage(content=instruction))

        # Generate the user message
        response = self.llm.invoke(self.messages)
        user_message = response.content.strip()

        # Clean up - remove any "User:" prefix if the model added one
        if user_message.lower().startswith("user:"):
            user_message = user_message[5:].strip()

        # Update history with what we generated (for context)
        self.messages.append(AIMessage(content=f"[You said]: {user_message}"))

        # Determine if conversation should end
        should_end = self.current_turn >= self.max_turns

        # Check for natural endings
        closing_indicators = ["thank", "thanks", "goodbye", "bye", "that's all", "appreciate", "helpful"]
        if any(indicator in user_message.lower() for indicator in closing_indicators):
            should_end = True

        return user_message, should_end


def slugify(text: str) -> str:
    """Convert text to a URL/identifier-friendly slug."""
    import re
    # Lowercase, replace spaces and special chars with underscores
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = re.sub(r'_+', '_', slug)  # Collapse multiple underscores
    slug = slug.strip('_')  # Remove leading/trailing underscores
    return slug


def create_posthog_client(
    session_id: Optional[str] = None,
    span_name: Optional[str] = None,
) -> Posthog:
    """Create a PostHog client with optional session ID and span name."""
    super_properties = {}
    if session_id:
        super_properties["$ai_session_id"] = session_id
    if span_name:
        super_properties["$ai_span_name"] = span_name

    return Posthog(
        os.getenv("POSTHOG_API_KEY"),
        host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
        super_properties=super_properties if super_properties else None,
    )


def create_provider(provider_key: str, posthog_client: Posthog):
    """Create a provider instance by key."""
    if provider_key not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_key}")

    name, provider_class = PROVIDERS[provider_key]
    return provider_class(posthog_client)


def get_response_from_provider(provider, message: str, verbose: bool = True) -> str:
    """Get a response from the provider, handling both streaming and non-streaming."""
    if hasattr(provider, 'chat_stream'):
        response_parts = []
        if verbose:
            print("Assistant: ", end="", flush=True)
        for chunk in provider.chat_stream(message):
            response_parts.append(chunk)
            if verbose:
                print(chunk, end="", flush=True)
        if verbose:
            print()
        return "".join(response_parts)
    else:
        response = provider.chat(message)
        if verbose:
            print(f"Assistant: {response}")
        return response


def run_conversation(
    provider_key: str,
    max_turns: int = 5,
    verbose: bool = True,
    delay_between_turns: float = 1.0,
    topic: Optional[str] = None,
    persona: Optional[str] = None,
    distinct_id: Optional[str] = None,
) -> dict:
    """
    Run a single conversation between the User Simulator and a provider.

    Returns a dict with conversation metadata.
    """
    # Select random topic and persona if not specified (do this first for span name)
    topic = topic or random.choice(TOPICS)
    persona = persona or random.choice(USER_PERSONAS)
    provider_name = PROVIDERS[provider_key][0]

    # Set distinct_id for this conversation (providers read from env var)
    conversation_distinct_id = distinct_id or f"user-{uuid.uuid4().hex[:8]}"
    os.environ["POSTHOG_DISTINCT_ID"] = conversation_distinct_id

    # Create span name: topic_provider (e.g., "weather_in_various_cities_openai_chat")
    span_name = f"{slugify(topic)}_{slugify(provider_name)}"

    # Create a new session for this conversation
    session_id = str(uuid.uuid4())
    posthog_client = create_posthog_client(session_id=session_id)

    # Create the target provider (this may set its own span name)
    provider = create_provider(provider_key, posthog_client)

    # Override the span name AFTER provider creation (providers set their own, we want ours)
    posthog_client.super_properties = {
        **(posthog_client.super_properties or {}),
        "$ai_span_name": span_name,
    }

    # Create the user simulator
    simulator = UserSimulator(topic=topic, persona=persona, max_turns=max_turns)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Session: {session_id}")
        print(f"Distinct ID: {conversation_distinct_id}")
        print(f"Span: {span_name}")
        print(f"Provider: {provider_name}")
        print(f"Topic: {topic}")
        print(f"Persona: {persona}")
        print(f"Max turns: {max_turns}")
        print(f"{'='*60}\n")

    conversation_history = []
    actual_turns = 0
    assistant_response = None

    while True:
        actual_turns += 1

        # Generate user message
        try:
            user_message, should_end = simulator.generate_message(assistant_response)
        except Exception as e:
            if verbose:
                print(f"Error generating user message: {e}")
            break

        if verbose:
            print(f"[Turn {actual_turns}]")
            print(f"User: {user_message}")

        conversation_history.append({"role": "user", "content": user_message})

        # Get response from provider
        try:
            assistant_response = get_response_from_provider(provider, user_message, verbose)
            conversation_history.append({"role": "assistant", "content": assistant_response})
        except Exception as e:
            if verbose:
                print(f"Error from provider: {e}")
            conversation_history.append({"role": "error", "content": str(e)})
            break

        if verbose:
            print()

        # Check if we should end
        if should_end:
            if verbose:
                print("[Conversation ended naturally]")
            break

        # Delay between turns
        time.sleep(delay_between_turns)

    # Flush PostHog events
    posthog_client.flush()

    return {
        "session_id": session_id,
        "distinct_id": conversation_distinct_id,
        "span_name": span_name,
        "provider": provider_name,
        "topic": topic,
        "persona": persona,
        "turns": actual_turns,
        "history": conversation_history,
    }


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Generate demo chat data for PostHog LLM Analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 5 conversations with random providers
  python generate_demo_data.py --conversations 5

  # Use specific providers only
  python generate_demo_data.py --providers openai_chat anthropic --conversations 3

  # Quick test with 3 turns per conversation
  python generate_demo_data.py --max-turns 3 --conversations 2

  # Quiet mode (no output)
  python generate_demo_data.py --quiet --conversations 10

  # Specify a topic
  python generate_demo_data.py --topic "weather in various cities" --conversations 3

  # Use a specific distinct ID for all conversations
  python generate_demo_data.py --distinct-id "demo-user@example.com" --conversations 3

  # Run 20 conversations in parallel with 5 workers
  python generate_demo_data.py --conversations 20 --parallel 5

Available providers:
  anthropic, anthropic_streaming, gemini, gemini_streaming,
  langchain, openai, openai_streaming, openai_chat,
  openai_chat_streaming, litellm, litellm_streaming
        """,
    )

    parser.add_argument(
        "-n", "--conversations",
        type=int,
        default=5,
        help="Number of conversations to generate (default: 5)",
    )
    parser.add_argument(
        "-t", "--max-turns",
        type=int,
        default=5,
        help="Maximum turns per conversation (default: 5)",
    )
    parser.add_argument(
        "-p", "--providers",
        nargs="+",
        choices=list(PROVIDERS.keys()),
        help="Specific providers to use (default: random from all available)",
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=1.0,
        help="Delay between turns in seconds (default: 1.0)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode - suppress conversation output",
    )
    parser.add_argument(
        "--topic",
        type=str,
        help="Specific topic for all conversations (default: random)",
    )
    parser.add_argument(
        "--persona",
        type=str,
        help="Specific persona for the user simulator (default: random)",
    )
    parser.add_argument(
        "--distinct-id",
        type=str,
        help="PostHog distinct ID for the simulated user (default: random UUID per conversation)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="Run N conversations in parallel (default: 1, sequential)",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List all available providers and exit",
    )
    parser.add_argument(
        "--list-topics",
        action="store_true",
        help="List all conversation topics and exit",
    )
    parser.add_argument(
        "--list-personas",
        action="store_true",
        help="List all user personas and exit",
    )

    args = parser.parse_args()

    # Handle list commands
    if args.list_providers:
        print("\nAvailable Providers:")
        print("=" * 50)
        for key, (name, _) in PROVIDERS.items():
            print(f"  {key:25} -> {name}")
        print()
        return

    if args.list_topics:
        print("\nConversation Topics:")
        print("=" * 50)
        for topic in TOPICS:
            print(f"  - {topic}")
        print()
        return

    if args.list_personas:
        print("\nUser Personas:")
        print("=" * 50)
        for persona in USER_PERSONAS:
            print(f"  - {persona}")
        print()
        return

    # Load environment variables
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

    # Validate environment
    if not os.getenv("POSTHOG_API_KEY"):
        print("Error: POSTHOG_API_KEY not set in environment")
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set (needed for User Simulator)")
        sys.exit(1)

    # Determine which providers to use
    available_providers = args.providers or list(PROVIDERS.keys())

    verbose = not args.quiet

    if verbose:
        print("\n" + "=" * 60)
        print("PostHog LLM Analytics Demo Data Generator")
        print("=" * 60)
        print(f"Conversations to generate: {args.conversations}")
        print(f"Max turns per conversation: {args.max_turns}")
        print(f"Providers: {', '.join(available_providers)}")
        print(f"Delay between turns: {args.delay}s")
        print(f"Parallel workers: {args.parallel}")
        if args.topic:
            print(f"Topic: {args.topic}")
        if args.persona:
            print(f"Persona: {args.persona}")
        if args.distinct_id:
            print(f"Distinct ID: {args.distinct_id}")
        else:
            print(f"Distinct ID: random per conversation")
        print("=" * 60)

    results = []

    # Helper function for running a single conversation (used by both sequential and parallel)
    def run_single_conversation(conv_index: int):
        provider_key = random.choice(available_providers)
        # In parallel mode, we use quiet mode to avoid jumbled output
        use_verbose = verbose and args.parallel == 1
        return run_conversation(
            provider_key=provider_key,
            max_turns=args.max_turns,
            verbose=use_verbose,
            delay_between_turns=args.delay,
            topic=args.topic,
            persona=args.persona,
            distinct_id=args.distinct_id,
        )

    if args.parallel > 1:
        # Parallel execution
        if verbose:
            print(f"\nRunning {args.conversations} conversations with {args.parallel} workers...")

        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_single_conversation, i): i
                for i in range(args.conversations)
            }

            completed = 0
            for future in as_completed(futures):
                conv_index = futures[future]
                completed += 1
                try:
                    result = future.result()
                    results.append(result)
                    if verbose:
                        print(f"[{completed}/{args.conversations}] {result['span_name']} - {result['turns']} turns")
                except Exception as e:
                    print(f"[{completed}/{args.conversations}] Error: {e}")
    else:
        # Sequential execution
        for i in range(args.conversations):
            if verbose:
                print(f"\n>>> Starting conversation {i + 1}/{args.conversations}")

            try:
                result = run_single_conversation(i)
                results.append(result)

                if verbose:
                    print(f"\n>>> Completed conversation {i + 1}/{args.conversations}")
                    print(f"    Session: {result['session_id']}")
                    print(f"    Span: {result['span_name']}")
                    print(f"    Turns: {result['turns']}")

            except Exception as e:
                print(f"\nError in conversation {i + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue

            # Small delay between conversations
            if i < args.conversations - 1:
                time.sleep(0.5)

    # Print summary
    if verbose and results:
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total conversations: {len(results)}")

        provider_counts = {}
        topic_counts = {}
        total_turns = 0

        for r in results:
            provider_counts[r["provider"]] = provider_counts.get(r["provider"], 0) + 1
            topic_counts[r["topic"]] = topic_counts.get(r["topic"], 0) + 1
            total_turns += r["turns"]

        print(f"Total turns: {total_turns}")
        print(f"\nBy Provider:")
        for provider, count in sorted(provider_counts.items()):
            print(f"  {provider}: {count}")

        print(f"\nBy Topic:")
        for topic, count in sorted(topic_counts.items()):
            print(f"  {topic}: {count}")

        print("=" * 60)
        print("Done! Check your PostHog dashboard for LLM analytics data.")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
