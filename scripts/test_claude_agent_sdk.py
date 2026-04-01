#!/usr/bin/env python3
"""
Claude Agent SDK test script for PostHog LLM Analytics.

Tests the posthog.ai.claude_agent_sdk integration by running a multi-turn
conversation with tool calls. Sends $ai_generation, $ai_span, and $ai_trace
events to the configured PostHog instance.

Usage:
    uv run scripts/test_claude_agent_sdk.py
    uv run scripts/test_claude_agent_sdk.py --prompt "What files are in the current directory?"
    uv run scripts/test_claude_agent_sdk.py --interactive
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _check_deps():
    missing = []
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        missing.append("claude-agent-sdk")
    try:
        import posthog  # noqa: F401
    except ImportError:
        missing.append("posthog")
    try:
        from posthog.ai.claude_agent_sdk import query  # noqa: F401
    except ImportError:
        missing.append("posthog (with claude_agent_sdk integration — needs posthog>=7.10.0)")
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Install with: uv add claude-agent-sdk posthog")
        sys.exit(1)


def _setup_posthog():
    from posthog import Posthog

    api_key = os.environ.get("POSTHOG_API_KEY")
    host = os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com")
    if not api_key:
        print("POSTHOG_API_KEY not set in environment. Events won't be sent.")
        return None
    return Posthog(api_key, host=host)


async def run_query(prompt: str, posthog_client, distinct_id: str, extra_props: dict):
    from claude_agent_sdk import ClaudeAgentOptions, AssistantMessage, ResultMessage
    from claude_agent_sdk.types import TextBlock, ToolUseBlock, StreamEvent
    from posthog.ai.claude_agent_sdk import query

    options = ClaudeAgentOptions(
        max_turns=10,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        permission_mode="bypassPermissions",
    )

    print(f"\n> {prompt}\n")

    async for message in query(
        prompt=prompt,
        options=options,
        posthog_client=posthog_client,
        posthog_distinct_id=distinct_id,
        posthog_properties=extra_props,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"  {block.text[:300]}")
                elif isinstance(block, ToolUseBlock):
                    print(f"  [tool] {block.name}({list(block.input.keys())})")
        elif isinstance(message, StreamEvent):
            event_type = message.event.get("type")
            if event_type == "message_start":
                print("  [streaming...]")
        elif isinstance(message, ResultMessage):
            print(f"\n  --- Result ---")
            print(f"  Cost: ${message.total_cost_usd}")
            print(f"  Turns: {message.num_turns}")
            print(f"  Duration: {message.duration_ms}ms")
            print(f"  Error: {message.is_error}")


async def run_interactive(posthog_client, distinct_id: str):
    from claude_agent_sdk import ClaudeAgentOptions, AssistantMessage, ResultMessage
    from claude_agent_sdk.types import TextBlock, ToolUseBlock
    from posthog.ai.claude_agent_sdk import instrument

    ph = instrument(
        client=posthog_client,
        distinct_id=distinct_id,
        properties={"app": "llm-analytics-apps", "mode": "interactive"},
    )

    options = ClaudeAgentOptions(
        max_turns=10,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        permission_mode="bypassPermissions",
    )

    print("\nClaude Agent SDK — Interactive Mode")
    print("Type 'quit' to exit\n")

    while True:
        try:
            prompt = input("> ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("quit", "exit", "q"):
                break

            async for message in ph.query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(f"  {block.text[:500]}")
                        elif isinstance(block, ToolUseBlock):
                            print(f"  [tool] {block.name}")
                elif isinstance(message, ResultMessage):
                    print(f"  [{message.num_turns} turns, ${message.total_cost_usd:.4f}]")
            print()

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [error] {e}")


def main():
    parser = argparse.ArgumentParser(description="Test Claude Agent SDK + PostHog LLM Analytics")
    parser.add_argument(
        "--prompt",
        default="List the files in the current directory and tell me what this project is about. Be brief.",
        help="Prompt to send",
    )
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive chat mode")
    parser.add_argument(
        "--distinct-id",
        default=os.environ.get("POSTHOG_DISTINCT_ID", "claude-agent-sdk-test"),
        help="PostHog distinct ID",
    )
    args = parser.parse_args()

    _check_deps()
    posthog_client = _setup_posthog()
    distinct_id = args.distinct_id

    extra_props = {
        "app": "llm-analytics-apps",
        "script": "test_claude_agent_sdk",
    }

    if args.interactive:
        asyncio.run(run_interactive(posthog_client, distinct_id))
    else:
        asyncio.run(run_query(args.prompt, posthog_client, distinct_id, extra_props))

    if posthog_client:
        posthog_client.shutdown()
        print("\nPostHog events flushed.")


if __name__ == "__main__":
    main()
