#!/usr/bin/env python3
"""
E2E test script for OTel → PostHog mapping with Pydantic AI.

Runs real Pydantic AI scenarios and sends OTel spans to PostHog for manual
verification. Each scenario exercises a different feature of the agent framework.

Usage:
    python scripts/test_pydantic_ai_otel.py          # Run all scenarios
    python scripts/test_pydantic_ai_otel.py 2         # Run scenario 2 only
    python scripts/test_pydantic_ai_otel.py 2 5 8     # Run scenarios 2, 5, and 8
"""

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(env_path, override=True)

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

MODEL = "gpt-4o-mini"

tracer_provider: TracerProvider | None = None


def setup_otel() -> TracerProvider:
    posthog_api_key = os.getenv("POSTHOG_API_KEY")
    posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")
    debug = os.getenv("DEBUG", "0") == "1"

    if not posthog_api_key:
        print("ERROR: POSTHOG_API_KEY must be set in .env")
        sys.exit(1)

    os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = f"{posthog_host}/i/v0/llma_otel"
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Bearer {posthog_api_key}"

    resource_attrs: dict[str, str] = {
        "service.name": "pydantic-ai-otel-test",
        "user.id": os.getenv("POSTHOG_DISTINCT_ID", "otel-test-user"),
    }
    if debug:
        resource_attrs["posthog.ai.debug"] = "true"

    provider = TracerProvider(resource=Resource.create(resource_attrs))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    Agent.instrument_all()
    return provider


def flush() -> None:
    if tracer_provider:
        tracer_provider.force_flush()


def header(num: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Scenario {num}: {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_1_simple_greeting() -> None:
    header(1, "Simple greeting (no tools)")
    agent = Agent(OpenAIChatModel(MODEL), system_prompt="You are a friendly assistant.")
    result = agent.run_sync("Hi, how are you?")
    print(f"  Response: {result.output[:120]}")
    flush()


def test_2_single_tool_call() -> None:
    header(2, "Single tool call (weather)")
    agent = Agent(OpenAIChatModel(MODEL), system_prompt="You help with weather.")

    @agent.tool
    def get_weather(ctx: RunContext[None], latitude: float, longitude: float, location_name: str) -> str:
        """Get current weather for a location."""
        return f"Weather in {location_name}: 15°C, sunny"

    result = agent.run_sync("What's the weather in Paris, France?")
    print(f"  Response: {result.output[:120]}")
    flush()


def test_3_multiple_tool_calls() -> None:
    header(3, "Multiple tool calls in one turn")
    agent = Agent(OpenAIChatModel(MODEL), system_prompt="You help with weather.")

    @agent.tool
    def get_weather(ctx: RunContext[None], latitude: float, longitude: float, location_name: str) -> str:
        """Get current weather for a location."""
        return f"Weather in {location_name}: 15°C, sunny"

    result = agent.run_sync("Compare the weather in Tokyo and London right now.")
    print(f"  Response: {result.output[:120]}")
    flush()


def test_4_structured_output() -> None:
    header(4, "Structured output (Pydantic model)")

    class CityInfo(BaseModel):
        name: str
        country: str
        population_estimate: str
        fun_fact: str

    agent = Agent(
        OpenAIChatModel(MODEL),
        output_type=CityInfo,
        system_prompt="Extract city information.",
    )
    result = agent.run_sync("Tell me about Montreal, Canada.")
    print(f"  Result: {result.output}")
    flush()


def test_5_model_retry() -> None:
    header(5, "Tool error with ModelRetry")
    call_count = 0

    agent = Agent(OpenAIChatModel(MODEL), system_prompt="You help find users.", retries=2)

    @agent.tool
    def find_user(ctx: RunContext[None], username: str) -> str:
        """Find a user by username."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ModelRetry("User not found, try searching by email instead")
        return f"Found user: {username}"

    result = agent.run_sync("Find the user named alice")
    print(f"  Response: {result.output[:120]}")
    print(f"  Tool was called {call_count} time(s)")
    flush()


def test_6_unrecoverable_error() -> None:
    header(6, "Unrecoverable tool error")
    agent = Agent(OpenAIChatModel(MODEL), system_prompt="You help with calculations.", retries=0)

    @agent.tool
    def divide(ctx: RunContext[None], a: float, b: float) -> str:
        """Divide two numbers."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return str(a / b)

    try:
        result = agent.run_sync("What is 10 divided by 0?")
        print(f"  Response: {result.output[:120]}")
    except Exception as e:
        print(f"  Expected error: {type(e).__name__}: {e}")
    flush()


def test_7_minimal_agent() -> None:
    header(7, "Minimal agent (no tools, no system prompt)")
    agent = Agent(OpenAIChatModel(MODEL))
    result = agent.run_sync("What is 2 + 2?")
    print(f"  Response: {result.output[:120]}")
    flush()


def test_8_multi_turn() -> None:
    header(8, "Multi-turn conversation (message_history)")
    agent = Agent(OpenAIChatModel(MODEL), system_prompt="You are a helpful assistant.")

    result1 = agent.run_sync("My name is Carlos.")
    print(f"  Turn 1: {result1.output[:120]}")
    flush()

    time.sleep(1)

    result2 = agent.run_sync("What's my name?", message_history=result1.all_messages())
    print(f"  Turn 2: {result2.output[:120]}")
    flush()


async def test_9_agent_delegation() -> None:
    header(9, "Agent delegation (sub-agent as tool)")

    research_agent = Agent(
        OpenAIChatModel(MODEL),
        system_prompt="You are a research expert. Give brief factual answers.",
    )

    main_agent = Agent(
        OpenAIChatModel(MODEL),
        system_prompt="You are a helpful assistant. Use the research tool for factual questions.",
    )

    @main_agent.tool
    async def research(ctx: RunContext[None], question: str) -> str:
        """Research a factual question."""
        result = await research_agent.run(question)
        return result.output

    result = await main_agent.run("What year was Python created?")
    print(f"  Response: {result.output[:120]}")
    flush()


def test_10_dynamic_system_prompt() -> None:
    header(10, "Dynamic system prompt with dependencies")
    agent = Agent(OpenAIChatModel(MODEL), deps_type=str)

    @agent.system_prompt
    def get_system_prompt(ctx: RunContext[str]) -> str:
        return f"You are a personal assistant for {ctx.deps}. Be friendly and use their name."

    result = agent.run_sync("What can you help me with?", deps="Carlos")
    print(f"  Response: {result.output[:120]}")
    flush()


def test_11_anthropic_provider() -> None:
    header(11, "Different provider (Anthropic)")

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("  SKIPPED: ANTHROPIC_API_KEY not set")
        return

    from pydantic_ai.models.anthropic import AnthropicModel

    agent = Agent(AnthropicModel("claude-sonnet-4-5-20250929"), system_prompt="Be brief.")
    result = agent.run_sync("Say hello in French.")
    print(f"  Response: {result.output[:120]}")
    flush()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

from typing import Any, Callable

SCENARIOS: dict[int, tuple[str, Callable[..., Any]]] = {
    1: ("Simple greeting", test_1_simple_greeting),
    2: ("Single tool call", test_2_single_tool_call),
    3: ("Multiple tool calls", test_3_multiple_tool_calls),
    4: ("Structured output", test_4_structured_output),
    5: ("ModelRetry", test_5_model_retry),
    6: ("Unrecoverable error", test_6_unrecoverable_error),
    7: ("Minimal agent", test_7_minimal_agent),
    8: ("Multi-turn", test_8_multi_turn),
    9: ("Agent delegation", test_9_agent_delegation),
    10: ("Dynamic system prompt", test_10_dynamic_system_prompt),
    11: ("Anthropic provider", test_11_anthropic_provider),
}


def main() -> None:
    global tracer_provider
    tracer_provider = setup_otel()

    debug = os.getenv("DEBUG", "0") == "1"
    host = os.getenv("POSTHOG_HOST", "http://localhost:8010")

    print("Pydantic AI OTel → PostHog E2E Test")
    print(f"  PostHog host: {host}")
    print(f"  Debug mode:   {debug}")
    print(f"  Model:        {MODEL}")

    if len(sys.argv) > 1:
        ids = [int(x) for x in sys.argv[1:]]
    else:
        ids = sorted(SCENARIOS.keys())

    for scenario_id in ids:
        if scenario_id not in SCENARIOS:
            print(f"\nUnknown scenario: {scenario_id}")
            continue
        _, fn = SCENARIOS[scenario_id]
        try:
            if asyncio.iscoroutinefunction(fn):
                asyncio.run(fn())
            else:
                fn()
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            flush()

    tracer_provider.shutdown()

    print(f"\n{'='*60}")
    print("  All done! Check PostHog → LLM analytics → Traces")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
