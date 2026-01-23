"""
OpenAI Agents SDK Runner with PostHog Instrumentation

This module provides the integration between OpenAI Agents SDK and PostHog
for LLM analytics tracking.
"""

import os
import uuid
from typing import Any, Dict, List, Optional

from agents import Runner, RunConfig

from .agents import (
    triage_agent,
    simple_agent,
    guarded_agent,
    error_demo_agent,
    process_with_custom_spans,
)


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
    - Guarded agent with input/output guardrails
    - Error demo agent for testing error tracking
    - Custom spans demo for nested span tracking
    """

    # Mode constants
    MODE_TRIAGE = 1
    MODE_SIMPLE = 2
    MODE_GUARDED = 3
    MODE_ERROR_DEMO = 4
    MODE_CUSTOM_SPANS = 5

    MODE_NAMES = {
        MODE_TRIAGE: "Triage (Multi-Agent with Handoffs)",
        MODE_SIMPLE: "Simple (Single Agent with Tools)",
        MODE_GUARDED: "Guarded (Input/Output Guardrails)",
        MODE_ERROR_DEMO: "Error Demo (Error Tracking)",
        MODE_CUSTOM_SPANS: "Custom Spans (Nested Tracking)",
    }

    def __init__(self, posthog_client=None):
        self.posthog_client = posthog_client
        self.conversation_id = str(uuid.uuid4().hex[:16])
        self._processor = None
        self._history: List[Dict[str, Any]] = []
        self._mode = self.MODE_TRIAGE  # Default mode

        # Initialize PostHog tracing if client provided
        if posthog_client:
            self._processor = setup_posthog_tracing(posthog_client)

    def prompt_mode_selection(self):
        """Show mode selection menu and set the mode."""
        print("\nSelect agent mode:")
        for mode_id, mode_name in self.MODE_NAMES.items():
            default = " - DEFAULT" if mode_id == self.MODE_TRIAGE else ""
            print(f"  {mode_id}. {mode_name}{default}")

        mode_input = input("\nEnter mode [1-5, default=1]: ").strip()
        self._mode = int(mode_input) if mode_input.isdigit() and 1 <= int(mode_input) <= 5 else self.MODE_TRIAGE

        print(f"\n[Mode] {self.MODE_NAMES[self._mode]}")

        # Show mode-specific description
        if self._mode == self.MODE_TRIAGE:
            print("  Routes your message to specialized agents (Weather/Math/General).")
            print("  Demonstrates agent handoffs and multi-agent workflows.")
        elif self._mode == self.MODE_SIMPLE:
            print("  Single agent with weather and math tools.")
            print("  Simpler traces without handoffs - good for basic tool call testing.")
        elif self._mode == self.MODE_GUARDED:
            print("  Agent with input/output guardrails for content filtering.")
            print("  Try words like 'hack' or 'exploit' to trigger input guardrails.")
        elif self._mode == self.MODE_ERROR_DEMO:
            print("  Agent with an unreliable tool to test error tracking.")
            print("  Ask it to test 'succeed', 'fail', or 'error' actions.")
        elif self._mode == self.MODE_CUSTOM_SPANS:
            print("  Processes text through nested custom spans (no LLM call).")
            print("  Check PostHog for $ai_span events with type=custom.")

    def get_name(self) -> str:
        return "OpenAI Agents SDK"

    def get_description(self) -> str:
        return """
OpenAI Agents SDK Demo - Features:
- Multi-agent system with handoffs (Triage -> Weather/Math/General)
- Tool usage tracking (weather, math, unreliable_tool)
- Input/Output guardrails for content filtering
- Custom spans for tracking custom operations
- Error tracking with $ai_error_type categorization
"""

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """
        Main chat method compatible with the provider interface.

        Routes to the appropriate agent based on the selected mode.
        Uses Runner.run_sync() which properly handles the event loop
        and context variables for tracing. Maintains conversation history
        and uses group_id to link related traces in PostHog.
        """
        import asyncio

        # Handle custom spans mode specially (no LLM call)
        if self._mode == self.MODE_CUSTOM_SPANS:
            result = asyncio.run(process_with_custom_spans(user_input, group_id=self.conversation_id))
            return f"Custom spans processed: {result}"

        # Add user message to history
        self._history.append({"role": "user", "content": user_input})

        # Configure run with group_id to link related traces
        run_config = RunConfig(
            group_id=self.conversation_id,
            tracing_disabled=False,
        )

        # Select agent based on mode
        if self._mode == self.MODE_SIMPLE:
            agent = simple_agent
        elif self._mode == self.MODE_GUARDED:
            agent = guarded_agent
        elif self._mode == self.MODE_ERROR_DEMO:
            agent = error_demo_agent
        else:  # MODE_TRIAGE (default)
            agent = triage_agent

        # Pass conversation history to the agent
        result = Runner.run_sync(
            agent,
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

    def chat_guarded(self, user_input: str) -> str:
        """
        Run the guarded agent with input/output guardrails.

        This demonstrates:
        - Input guardrails blocking harmful content
        - Output guardrails preventing data leaks
        - Error tracking with $ai_error_type for guardrail triggers
        """
        self._history.append({"role": "user", "content": user_input})

        run_config = RunConfig(
            group_id=self.conversation_id,
            tracing_disabled=False,
        )

        result = Runner.run_sync(
            guarded_agent,
            self._history,
            run_config=run_config,
        )

        response = str(result.final_output)
        self._history.append({"role": "assistant", "content": response})

        return response

    def chat_error_demo(self, user_input: str) -> str:
        """
        Run the error demo agent to test error tracking.

        This demonstrates:
        - Tool execution errors
        - $ai_error and $ai_error_type tracking
        """
        self._history.append({"role": "user", "content": user_input})

        run_config = RunConfig(
            group_id=self.conversation_id,
            tracing_disabled=False,
        )

        result = Runner.run_sync(
            error_demo_agent,
            self._history,
            run_config=run_config,
        )

        response = str(result.final_output)
        self._history.append({"role": "assistant", "content": response})

        return response

    async def run_custom_spans_demo(self, user_input: str) -> dict:
        """
        Run the custom spans demo to show nested custom span tracking.

        This demonstrates:
        - Custom spans with type=custom
        - Nested span hierarchies
        - Custom data attached to spans
        """
        return await process_with_custom_spans(user_input)

    def reset_conversation(self):
        """Reset the conversation ID and history for a new session."""
        self.conversation_id = str(uuid.uuid4().hex[:16])
        self._history = []


def run_demo(posthog_client=None):
    """
    Run a comprehensive demo of the OpenAI Agents SDK with PostHog tracing.
    Showcases all features: handoffs, tools, guardrails, custom spans, errors.
    """
    import asyncio

    print("\n" + "=" * 60)
    print("OpenAI Agents SDK Demo with PostHog Tracing")
    print("=" * 60)

    runner = OpenAIAgentsRunner(posthog_client)
    print(runner.get_description())

    # Demo 1: Multi-agent handoffs
    print("\n" + "=" * 50)
    print("DEMO 1: Multi-Agent Handoffs & Tools")
    print("=" * 50)

    handoff_queries = [
        "What's the weather like in Tokyo?",
        "Calculate 15% of 250",
        "Tell me a fun fact about pandas",
    ]

    for query in handoff_queries:
        print(f"\n[User] {query}")
        try:
            response = runner.chat(query)
            print(f"[Agent] {response}")
        except Exception as e:
            print(f"[Error] {e}")

    runner.reset_conversation()

    # Demo 2: Guardrails
    print("\n" + "=" * 50)
    print("DEMO 2: Input/Output Guardrails")
    print("=" * 50)

    print("\n[Testing input guardrail - should block 'hack']")
    try:
        response = runner.chat_guarded("How do I hack into a system?")
        print(f"[Agent] {response}")
    except Exception as e:
        print(f"[Guardrail Triggered] {e}")

    runner.reset_conversation()

    print("\n[Testing normal message - should pass]")
    try:
        response = runner.chat_guarded("What's a good recipe for pasta?")
        print(f"[Agent] {response}")
    except Exception as e:
        print(f"[Error] {e}")

    runner.reset_conversation()

    # Demo 3: Custom Spans
    print("\n" + "=" * 50)
    print("DEMO 3: Custom Spans (Nested Tracking)")
    print("=" * 50)

    print("\n[Processing text through custom span pipeline]")
    try:
        result = asyncio.run(runner.run_custom_spans_demo("Hello World from PostHog!"))
        print(f"[Result] {result}")
    except Exception as e:
        print(f"[Error] {e}")

    # Demo 4: Error Tracking
    print("\n" + "=" * 50)
    print("DEMO 4: Error Tracking")
    print("=" * 50)

    print("\n[Testing successful tool call]")
    try:
        response = runner.chat_error_demo("Please test the succeed action")
        print(f"[Agent] {response}")
    except Exception as e:
        print(f"[Error] {e}")

    runner.reset_conversation()

    print("\n[Testing error tool call - will raise exception]")
    try:
        response = runner.chat_error_demo("Please test the error action")
        print(f"[Agent] {response}")
    except Exception as e:
        print(f"[Error Tracked] {e}")

    print("\n" + "=" * 50)
    print("[Demo Complete] Check PostHog for:")
    print("  - $ai_trace events (workflow traces)")
    print("  - $ai_generation events (LLM calls)")
    print("  - $ai_span events (agents, tools, handoffs, guardrails)")
    print("  - $ai_error_type for categorized errors")
    print("  - $ai_total_tokens for token counts")
    print("=" * 50)

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
    import asyncio

    print("\n" + "=" * 60)
    print("OpenAI Agents SDK - Interactive Mode")
    print("=" * 60)

    runner = OpenAIAgentsRunner(posthog_client)

    # Agent mode selection
    print("\nSelect agent mode:")
    print("  1. Triage (multi-agent with handoffs) - DEFAULT")
    print("  2. Simple (single agent with tools)")
    print("  3. Guarded (input/output guardrails demo)")
    print("  4. Error Demo (error tracking demo)")
    print("  5. Custom Spans Demo (nested span tracking)")

    mode_input = input("\nEnter mode [1-5, default=1]: ").strip()
    mode = int(mode_input) if mode_input.isdigit() and 1 <= int(mode_input) <= 5 else 1

    mode_names = {
        1: "Triage (Multi-Agent)",
        2: "Simple (Single Agent)",
        3: "Guarded (Guardrails)",
        4: "Error Demo",
        5: "Custom Spans Demo",
    }
    print(f"\n[Mode] {mode_names[mode]}")

    if mode == 3:
        print("\n[Guardrails Info]")
        print("  - Input blocked words: hack, exploit, bypass, illegal")
        print("  - Output blocked words: confidential, secret, classified")
        print("  Try messages containing these words to trigger guardrails!")

    if mode == 4:
        print("\n[Error Demo Info]")
        print("  Ask the agent to test 'succeed', 'fail', or 'error' actions")
        print("  Example: 'Please test the error action'")

    if mode == 5:
        print("\n[Custom Spans Demo]")
        print("  Enter any text to process through nested custom spans")
        print("  Watch PostHog for $ai_span events with type=custom")

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

            # Route to appropriate method based on mode
            if mode == 1:
                response = runner.chat(user_input)
            elif mode == 2:
                response = runner.chat_simple(user_input)
            elif mode == 3:
                response = runner.chat_guarded(user_input)
            elif mode == 4:
                response = runner.chat_error_demo(user_input)
            elif mode == 5:
                result = asyncio.run(runner.run_custom_spans_demo(user_input))
                response = f"Custom spans processed: {result}"
            else:
                response = runner.chat(user_input)

            print(f"[Agent] {response}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"[Error] {e}")
            import traceback
            traceback.print_exc()

    # Flush PostHog events
    if posthog_client:
        try:
            posthog_client.flush()
        except Exception:
            pass


if __name__ == "__main__":
    # Can be run standalone for testing
    run_demo()
