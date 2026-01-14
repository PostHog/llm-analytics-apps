"""
OpenAI Agents SDK Runner with PostHog Instrumentation

This module provides the integration between OpenAI Agents SDK and PostHog
for LLM analytics tracking.
"""

import os
import uuid
from typing import Any, Dict, List, Optional

from agents import Runner, RunConfig

from .agents import triage_agent, simple_agent


def setup_posthog_tracing(posthog_client, distinct_id: Optional[str] = None):
    """
    Initialize PostHog tracing for OpenAI Agents SDK.

    This registers a PostHogTracingProcessor with the Agents SDK that
    automatically captures all traces, spans, and generations.
    """
    try:
        from posthog.ai.openai_agents import instrument

        processor = instrument(
            client=posthog_client,
            distinct_id=distinct_id or os.getenv("POSTHOG_DISTINCT_ID", "openai-agents-user"),
            privacy_mode=False,
            properties={
                "app": "llm-analytics-apps",
                "agent_type": "openai-agents-sdk",
            }
        )
        print("[PostHog] OpenAI Agents SDK instrumentation enabled")
        return processor
    except ImportError as e:
        print(f"[PostHog] Warning: Could not enable instrumentation: {e}")
        print("[PostHog] Make sure posthog-python is installed with OpenAI agents support")
        return None
    except Exception as e:
        print(f"[PostHog] Error enabling instrumentation: {e}")
        return None


class OpenAIAgentsRunner:
    """
    Runner class for OpenAI Agents SDK examples with PostHog integration.

    Supports multiple modes:
    - Multi-agent with handoffs (triage -> specialized agents)
    - Single agent with tools
    """

    def __init__(self, posthog_client=None):
        self.posthog_client = posthog_client
        self.conversation_id = str(uuid.uuid4().hex[:16])
        self._processor = None
        self._history: List[Dict[str, Any]] = []

        # Initialize PostHog tracing if client provided
        if posthog_client:
            self._processor = setup_posthog_tracing(posthog_client)

    def get_name(self) -> str:
        return "OpenAI Agents SDK"

    def get_description(self) -> str:
        return """
Multi-agent system with handoffs:
- TriageAgent: Routes to specialized agents
- WeatherAgent: Weather queries with tool
- MathAgent: Calculations with tool
- GeneralAgent: General conversation
"""

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """
        Main chat method compatible with the provider interface.

        Uses Runner.run_sync() which properly handles the event loop
        and context variables for tracing. Maintains conversation history
        and uses group_id to link related traces in PostHog.
        """
        # Add user message to history
        self._history.append({"role": "user", "content": user_input})

        # Configure run with group_id to link related traces
        run_config = RunConfig(
            group_id=self.conversation_id,
            tracing_disabled=False,
        )

        # Pass conversation history to the agent
        result = Runner.run_sync(
            triage_agent,
            self._history,
            run_config=run_config,
        )

        # Add assistant response to history
        response = str(result.final_output)
        self._history.append({"role": "assistant", "content": response})

        return response

    def chat_simple(self, user_input: str) -> str:
        """Run the simple single agent with tools."""
        self._history.append({"role": "user", "content": user_input})

        run_config = RunConfig(
            group_id=self.conversation_id,
            tracing_disabled=False,
        )

        result = Runner.run_sync(
            simple_agent,
            self._history,
            run_config=run_config,
        )

        response = str(result.final_output)
        self._history.append({"role": "assistant", "content": response})

        return response

    def reset_conversation(self):
        """Reset the conversation ID and history for a new session."""
        self.conversation_id = str(uuid.uuid4().hex[:16])
        self._history = []


def run_demo(posthog_client=None):
    """
    Run an interactive demo of the OpenAI Agents SDK with PostHog tracing.
    """
    print("\n" + "=" * 60)
    print("OpenAI Agents SDK Demo with PostHog Tracing")
    print("=" * 60)

    runner = OpenAIAgentsRunner(posthog_client)
    print(runner.get_description())

    # Demo queries to showcase different agents
    demo_queries = [
        "What's the weather like in Tokyo?",
        "Calculate 15% of 250",
        "Tell me a fun fact about pandas",
    ]

    print("\nRunning demo queries:")
    print("-" * 40)

    for query in demo_queries:
        print(f"\n[User] {query}")
        try:
            response = runner.chat(query)
            print(f"[Agent] {response}")
        except Exception as e:
            print(f"[Error] {e}")
        print("-" * 40)

    print("\n[Demo Complete] Check PostHog for traces!")

    # Flush PostHog events
    if posthog_client:
        try:
            posthog_client.flush()
        except Exception:
            pass


def run_interactive(posthog_client=None):
    """
    Run an interactive chat session with the OpenAI Agents SDK.
    """
    print("\n" + "=" * 60)
    print("OpenAI Agents SDK - Interactive Mode")
    print("=" * 60)

    runner = OpenAIAgentsRunner(posthog_client)
    print(runner.get_description())
    print("\nType 'quit' or 'q' to exit, 'reset' to start a new conversation")
    print("-" * 60)

    while True:
        try:
            user_input = input("\n[You] ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'q', 'exit']:
                print("\nGoodbye!")
                break

            if user_input.lower() == 'reset':
                runner.reset_conversation()
                print("[System] Conversation reset")
                continue

            response = runner.chat(user_input)
            print(f"[Agent] {response}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"[Error] {e}")

    # Flush PostHog events
    if posthog_client:
        try:
            posthog_client.flush()
        except Exception:
            pass


if __name__ == "__main__":
    # Can be run standalone for testing
    run_demo()
