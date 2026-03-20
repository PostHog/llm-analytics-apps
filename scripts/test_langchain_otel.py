#!/usr/bin/env python3
"""
E2E test script for OTel → PostHog mapping with LangChain.

Runs real LangChain scenarios and sends OTel spans to PostHog for manual
verification. Each scenario exercises a different feature of the framework.

Usage:
    python scripts/test_langchain_otel.py          # Run all scenarios
    python scripts/test_langchain_otel.py 2         # Run scenario 2 only
    python scripts/test_langchain_otel.py 2 5 8     # Run scenarios 2, 5, and 8
"""

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path, override=True)

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

MODEL = "gpt-4o-mini"

tracer_provider: TracerProvider | None = None


def setup_otel() -> TracerProvider:
    posthog_api_key = os.getenv("POSTHOG_API_KEY")
    posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")
    debug = os.getenv("DEBUG", "0") == "1"

    if not posthog_api_key:
        print("ERROR: POSTHOG_API_KEY must be set in .env")
        sys.exit(1)

    os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = f"{posthog_host}/i/v0/ai/otel"
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Bearer {posthog_api_key}"

    resource_attrs: dict[str, str] = {
        "service.name": "langchain-otel-test",
        "user.id": os.getenv("POSTHOG_DISTINCT_ID", "otel-test-user"),
    }
    if debug:
        resource_attrs["posthog.ai.debug"] = "true"

    provider = TracerProvider(resource=Resource.create(resource_attrs))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    LangchainInstrumentor().instrument()
    return provider


def flush() -> None:
    if tracer_provider:
        tracer_provider.force_flush()


def header(num: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Scenario {num}: {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def get_weather(latitude: float, longitude: float, location_name: str) -> str:
    """Get current weather for a location."""
    return f"Weather in {location_name}: 15°C, sunny"


@tool
def tell_joke(setup: str, punchline: str) -> str:
    """Tell a joke with a setup and punchline."""
    return f"{setup}\n\n{punchline}"


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_1_simple_greeting() -> None:
    header(1, "Simple greeting (no tools)")
    model = ChatOpenAI(model=MODEL, temperature=0)
    messages = [
        SystemMessage(content="You are a friendly assistant."),
        HumanMessage(content="Hi, how are you?"),
    ]
    result = model.invoke(messages)
    print(f"  Response: {str(result.content)[:120]}")
    flush()


def test_2_single_tool_call() -> None:
    header(2, "Single tool call (weather)")
    model = ChatOpenAI(model=MODEL, temperature=0)
    model_with_tools = model.bind_tools([get_weather])
    messages = [
        SystemMessage(content="You help with weather."),
        HumanMessage(content="What's the weather in Paris, France?"),
    ]
    response = model_with_tools.invoke(messages)

    if response.tool_calls:
        for tc in response.tool_calls:
            result = get_weather.invoke(tc["args"])
            messages.append(response)
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        final = model_with_tools.invoke(messages)
        print(f"  Response: {str(final.content)[:120]}")
    else:
        print(f"  Response: {str(response.content)[:120]}")
    flush()


def test_3_multiple_tool_calls() -> None:
    header(3, "Multiple tool calls in one turn")
    model = ChatOpenAI(model=MODEL, temperature=0)
    model_with_tools = model.bind_tools([get_weather])
    messages = [
        SystemMessage(content="You help with weather."),
        HumanMessage(content="Compare the weather in Tokyo and London right now."),
    ]
    response = model_with_tools.invoke(messages)

    if response.tool_calls:
        messages.append(response)
        for tc in response.tool_calls:
            result = get_weather.invoke(tc["args"])
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        final = model_with_tools.invoke(messages)
        print(f"  Response: {str(final.content)[:120]}")
    else:
        print(f"  Response: {str(response.content)[:120]}")
    flush()


def test_4_structured_output() -> None:
    header(4, "Structured output (with_structured_output)")
    from pydantic import BaseModel

    class CityInfo(BaseModel):
        name: str
        country: str
        population_estimate: str
        fun_fact: str

    model = ChatOpenAI(model=MODEL, temperature=0)
    structured = model.with_structured_output(CityInfo)
    result = structured.invoke("Tell me about Montreal, Canada.")
    print(f"  Result: {result}")
    flush()


def test_5_tool_error_handling() -> None:
    header(5, "Tool that raises an error")

    @tool
    def divide(a: float, b: float) -> str:
        """Divide two numbers."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return str(a / b)

    model = ChatOpenAI(model=MODEL, temperature=0)
    model_with_tools = model.bind_tools([divide])
    messages = [
        SystemMessage(content="You help with calculations."),
        HumanMessage(content="What is 10 divided by 0?"),
    ]
    response = model_with_tools.invoke(messages)

    if response.tool_calls:
        messages.append(response)
        for tc in response.tool_calls:
            try:
                result = divide.invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            except Exception as e:
                messages.append(ToolMessage(content=f"Error: {e}", tool_call_id=tc["id"]))
                print(f"  Tool error: {e}")

        final = model_with_tools.invoke(messages)
        print(f"  Response: {str(final.content)[:120]}")
    else:
        print(f"  Response: {str(response.content)[:120]}")
    flush()


def test_6_minimal_invocation() -> None:
    header(6, "Minimal invocation (no tools, no system prompt)")
    model = ChatOpenAI(model=MODEL, temperature=0)
    result = model.invoke("What is 2 + 2?")
    print(f"  Response: {str(result.content)[:120]}")
    flush()


def test_7_multi_turn() -> None:
    header(7, "Multi-turn conversation")
    model = ChatOpenAI(model=MODEL, temperature=0)
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="My name is Carlos."),
    ]
    result1 = model.invoke(messages)
    print(f"  Turn 1: {str(result1.content)[:120]}")
    flush()

    time.sleep(1)

    messages.append(result1)
    messages.append(HumanMessage(content="What's my name?"))
    result2 = model.invoke(messages)
    print(f"  Turn 2: {str(result2.content)[:120]}")
    flush()


def test_8_multiple_tools() -> None:
    header(8, "Multiple different tools available")
    model = ChatOpenAI(model=MODEL, temperature=0)
    model_with_tools = model.bind_tools([get_weather, tell_joke])
    messages = [
        SystemMessage(content="You are a helpful assistant with weather and joke tools."),
        HumanMessage(content="Tell me a joke about the weather."),
    ]
    response = model_with_tools.invoke(messages)

    if response.tool_calls:
        messages.append(response)
        tool_map = {"get_weather": get_weather, "tell_joke": tell_joke}
        for tc in response.tool_calls:
            if tc["name"] in tool_map:
                result = tool_map[tc["name"]].invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        final = model_with_tools.invoke(messages)
        print(f"  Response: {str(final.content)[:120]}")
    else:
        print(f"  Response: {str(response.content)[:120]}")
    flush()


def test_9_chain_composition() -> None:
    header(9, "Chain composition (prompt | model)")
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a travel expert. Be concise."),
        ("user", "What are the top 3 things to do in {city}?"),
    ])
    model = ChatOpenAI(model=MODEL, temperature=0)
    chain = prompt | model
    result = chain.invoke({"city": "Montreal"})
    print(f"  Response: {str(result.content)[:120]}")
    flush()


def test_10_anthropic_provider() -> None:
    header(10, "Different provider (Anthropic via ChatAnthropic)")

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("  SKIPPED: ANTHROPIC_API_KEY not set")
        return

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        print("  SKIPPED: langchain-anthropic not installed")
        return

    model = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)
    messages = [
        SystemMessage(content="Be brief."),
        HumanMessage(content="Say hello in French."),
    ]
    result = model.invoke(messages)
    print(f"  Response: {str(result.content)[:120]}")
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
    5: ("Tool error handling", test_5_tool_error_handling),
    6: ("Minimal invocation", test_6_minimal_invocation),
    7: ("Multi-turn", test_7_multi_turn),
    8: ("Multiple tools", test_8_multiple_tools),
    9: ("Chain composition", test_9_chain_composition),
    10: ("Anthropic provider", test_10_anthropic_provider),
}


def main() -> None:
    global tracer_provider
    tracer_provider = setup_otel()

    debug = os.getenv("DEBUG", "0") == "1"
    host = os.getenv("POSTHOG_HOST", "http://localhost:8010")

    print("LangChain OTel → PostHog E2E Test")
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
