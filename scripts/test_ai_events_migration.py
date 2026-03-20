#!/usr/bin/env python3
"""
Generate test data for validating the ai_events ClickHouse table migration.

Creates events covering all LLM Analytics features via the PostHog capture API.
Each run is tagged with a --batch-label so events from different migration states
(S1-S5) are distinguishable in the UI.

Usage:
    cd /path/to/llm-analytics-apps
    uv run scripts/test_ai_events_migration.py --batch-label S1

Environment:
    POSTHOG_HOST        PostHog instance URL (default: http://localhost:8010)
    POSTHOG_API_KEY     Project API key (auto-fetched from localhost if not set)
    POSTHOG_DISTINCT_ID Distinct ID for generated events (default: ai-events-migration-test)
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone


POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8010")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
DISTINCT_ID = os.getenv("POSTHOG_DISTINCT_ID", "ai-events-migration-test")


def get_api_key() -> str:
    global POSTHOG_API_KEY
    if POSTHOG_API_KEY:
        return POSTHOG_API_KEY

    print("POSTHOG_API_KEY not set, attempting to fetch from localhost...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    helper = os.path.join(script_dir, "get_localhost_api_key.py")
    try:
        result = subprocess.run(
            [sys.executable, helper, "--host", POSTHOG_HOST, "--quiet"],
            capture_output=True,
            text=True,
            check=True,
        )
        POSTHOG_API_KEY = result.stdout.strip()
        print(f"  Got API key: {POSTHOG_API_KEY[:8]}...")
        return POSTHOG_API_KEY
    except Exception as e:
        print(f"  Failed: {e}")
        print("  Set POSTHOG_API_KEY manually.")
        sys.exit(1)


def capture_event(event: str, properties: dict, timestamp: str | None = None) -> None:
    payload = {
        "api_key": get_api_key(),
        "event": event,
        "properties": {
            "$lib": "posthog-python",
            "$lib_version": "0.0.0-migration-test",
            "distinct_id": DISTINCT_ID,
            **properties,
        },
        "distinct_id": DISTINCT_ID,
    }
    if timestamp:
        payload["timestamp"] = timestamp

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{POSTHOG_HOST}/capture/",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        resp.read()


def ts(base: datetime, offset_seconds: float) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def random_uuid() -> str:
    return str(uuid.uuid4())


def output_choices(content: str) -> list[dict]:
    """Wrap a string into the $ai_output_choices format the UI expects."""
    return [{"role": "assistant", "content": [{"type": "text", "text": content}]}]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_simple_generation(label: str, base: datetime, session_id: str) -> dict:
    """1. Standalone generation: single $ai_generation (direct SDK wrapper pattern)."""
    trace_id = random_uuid()
    gen_id = random_uuid()

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-chat-completion",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 1.23,
        "$ai_input_tokens": 150,
        "$ai_output_tokens": 80,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_model_parameters": {"temperature": 0.7, "max_tokens": 1000},
        "$ai_input": [{"role": "user", "content": f"[{label}] What is the capital of France?"}],
        "$ai_output_choices": output_choices(f"[{label}] The capital of France is Paris."),
    }, timestamp=ts(base, 1.23))

    return {"scenario": "simple-generation", "trace_id": trace_id, "gen_id": gen_id}


def scenario_nested_trace(label: str, base: datetime, session_id: str) -> dict:
    """2. Nested trace: $ai_trace -> $ai_span (agent) -> 2x $ai_generation."""
    trace_id = random_uuid()
    span_id = random_uuid()
    gen1_id = random_uuid()
    gen2_id = random_uuid()

    capture_event("$ai_trace", {
        "$ai_trace_id": trace_id,
        "$ai_span_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_trace_name": f"{label}-nested-trace",
        "$ai_span_name": f"{label}-nested-trace",
    }, timestamp=ts(base, 0))

    capture_event("$ai_span", {
        "$ai_trace_id": trace_id,
        "$ai_span_id": span_id,
        "$ai_parent_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": "agent-executor",
        "$ai_latency": 3.5,
    }, timestamp=ts(base, 0.1))

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_span_id": gen1_id,
        "$ai_parent_id": span_id,
        "$ai_session_id": session_id,
        "$ai_span_name": "plan-step",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 1.2,
        "$ai_input_tokens": 200,
        "$ai_output_tokens": 100,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_input": [
            {"role": "system", "content": "You are a planning agent. Break the user's task into concrete steps."},
            {"role": "user", "content": f"[{label}] Research the history of the Eiffel Tower and write a summary."},
        ],
        "$ai_output_choices": output_choices(f"[{label}] Step 1: Find construction dates and key architects. Step 2: Identify historical significance. Step 3: Compile into a 3-paragraph summary."),
    }, timestamp=ts(base, 1.3))

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_span_id": gen2_id,
        "$ai_parent_id": span_id,
        "$ai_session_id": session_id,
        "$ai_span_name": "execute-step",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 2.1,
        "$ai_input_tokens": 350,
        "$ai_output_tokens": 150,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_input": [
            {"role": "system", "content": "Execute the provided plan and produce the final result."},
            {"role": "user", "content": f"[{label}] Plan: 1) Find construction dates and key architects 2) Identify historical significance 3) Compile into a summary."},
        ],
        "$ai_output_choices": output_choices(f"[{label}] The Eiffel Tower was built between 1887 and 1889 by engineer Gustave Eiffel for the 1889 World's Fair in Paris. Originally controversial, it has become the most iconic symbol of France, attracting nearly 7 million visitors per year."),
    }, timestamp=ts(base, 3.4))

    return {"scenario": "nested-trace", "trace_id": trace_id}


def scenario_tools_generation(label: str, base: datetime, session_id: str) -> dict:
    """3. Standalone generation with tools: $ai_tools and tool calls in $ai_output_choices."""
    trace_id = random_uuid()
    gen_id = random_uuid()

    tools = [
        {"type": "function", "function": {"name": "get_weather", "description": "Get current weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}},
        {"type": "function", "function": {"name": "search_docs", "description": "Search documentation", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}},
    ]

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-tool-calling-step",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 2.5,
        "$ai_input_tokens": 300,
        "$ai_output_tokens": 120,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_tools": tools,
        "$ai_output_choices": [{
            "role": "assistant",
            "content": [
                {"type": "function", "id": "call_abc123", "function": {"name": "get_weather", "arguments": '{"city": "London"}'}},
                {"type": "function", "id": "call_def456", "function": {"name": "search_docs", "arguments": '{"query": "API rate limits"}'}},
            ],
        }],
        "$ai_input": [{"role": "user", "content": f"[{label}] What's the weather in London? Also find the docs about API rate limits."}],
    }, timestamp=ts(base, 2.5))

    return {"scenario": "tools-generation", "trace_id": trace_id}


def scenario_error_generation(label: str, base: datetime, session_id: str) -> dict:
    """4. Standalone generation with error: error properties on the generation itself."""
    trace_id = random_uuid()
    gen_id = random_uuid()

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-failing-completion",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 0.5,
        "$ai_is_error": True,
        "$ai_error": "Rate limit exceeded for model gpt-4o (request req_abc123)",
        "$ai_http_status": 429,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_input": [{"role": "user", "content": f"[{label}] Translate this paragraph into Spanish."}],
    }, timestamp=ts(base, 0.5))

    return {"scenario": "error-generation", "trace_id": trace_id}


def scenario_heavy_props_generation(label: str, base: datetime, session_id: str) -> dict:
    """5. Standalone generation with all 6 heavy properties set."""
    trace_id = random_uuid()
    gen_id = random_uuid()

    input_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"[{label}] What is the weather in London?"},
    ]
    output_text = f"[{label}] The weather in London is currently 15°C with light rain."
    input_state = {"conversation_id": f"{label}-conv-001", "turn": 3}
    output_state = {"conversation_id": f"{label}-conv-001", "turn": 4}
    tools_def = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a location",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }
    ]

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-heavy-completion",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 1.8,
        "$ai_input_tokens": 250,
        "$ai_output_tokens": 90,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_model_parameters": {"temperature": 0.7, "max_tokens": 1000},
        "$ai_input": input_messages,
        "$ai_output_choices": output_choices(output_text),
        "$ai_input_state": input_state,
        "$ai_output_state": output_state,
        "$ai_tools": tools_def,
    }, timestamp=ts(base, 1.8))

    return {"scenario": "heavy-props-generation", "trace_id": trace_id, "gen_id": gen_id}


def scenario_embedding(label: str, base: datetime, session_id: str) -> dict:
    """6. Standalone embedding event from a different provider."""
    trace_id = random_uuid()
    emb_id = random_uuid()

    capture_event("$ai_embedding", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-embed-query",
        "$ai_model": "embed-english-v3.0",
        "$ai_provider": "cohere",
        "$ai_latency": 0.3,
        "$ai_input_tokens": 45,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.cohere.com/v1",
        "$ai_input": f"[{label}] What is retrieval-augmented generation?",
    }, timestamp=ts(base, 0.3))

    return {"scenario": "embedding", "trace_id": trace_id}


def scenario_multi_provider(label: str, base: datetime, session_id: str) -> dict:
    """7. Multi-provider: two standalone generations (openai + anthropic) sharing a trace_id."""
    trace_id = random_uuid()
    gen1_id = random_uuid()
    gen2_id = random_uuid()

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-openai-step",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 1.5,
        "$ai_input_tokens": 200,
        "$ai_output_tokens": 100,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_input": [{"role": "user", "content": f"[{label}] Draft a short email to the team about the updated deployment process."}],
        "$ai_output_choices": output_choices(f"[{label}] Subject: Updated Deployment Process\n\nHi team,\n\nWe've rolled out a new deployment pipeline. Key changes: automated staging deploys on merge, mandatory canary period before production, and rollback via a single CLI command. Please review the updated runbook by Friday.\n\nThanks"),
    }, timestamp=ts(base, 1.5))

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-anthropic-step",
        "$ai_model": "claude-sonnet-4-20250514",
        "$ai_provider": "anthropic",
        "$ai_latency": 2.0,
        "$ai_input_tokens": 180,
        "$ai_output_tokens": 120,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.anthropic.com/v1",
        "$ai_input": [
            {"role": "user", "content": f"[{label}] Review this draft email for tone and clarity:\n\nSubject: Updated Deployment Process\n\nHi team,\n\nWe've rolled out a new deployment pipeline. Key changes: automated staging deploys on merge, mandatory canary period before production, and rollback via a single CLI command. Please review the updated runbook by Friday.\n\nThanks"},
        ],
        "$ai_output_choices": output_choices(f"[{label}] The email is clear and concise. Two suggestions: 1) Add a link to the runbook so readers can find it easily. 2) Mention who to contact with questions."),
    }, timestamp=ts(base, 3.5))

    return {"scenario": "multi-provider", "trace_id": trace_id}


def scenario_session_with_traces(label: str, base: datetime) -> dict:
    """8. Session with 3 separate traces sharing the same session_id."""
    session_id = f"{label}-multi-trace-session"
    trace_ids = []

    session_messages: list[list[dict]] = [
        [
            {"role": "user", "content": f"[{label}] How do I create a Python virtual environment?"},
        ],
        [
            {"role": "user", "content": f"[{label}] How do I create a Python virtual environment?"},
            {"role": "assistant", "content": f"[{label}] Run `python -m venv .venv` to create it, then `source .venv/bin/activate` to activate."},
            {"role": "user", "content": f"[{label}] Now install requests and flask in it."},
        ],
        [
            {"role": "user", "content": f"[{label}] How do I create a Python virtual environment?"},
            {"role": "assistant", "content": f"[{label}] Run `python -m venv .venv` to create it, then `source .venv/bin/activate` to activate."},
            {"role": "user", "content": f"[{label}] Now install requests and flask in it."},
            {"role": "assistant", "content": f"[{label}] With the venv active, run `pip install requests flask`."},
            {"role": "user", "content": f"[{label}] Write a minimal Flask hello-world app."},
        ],
    ]
    session_outputs = [
        f"[{label}] Run `python -m venv .venv` to create it, then `source .venv/bin/activate` to activate.",
        f"[{label}] With the venv active, run `pip install requests flask`.",
        (
            f"[{label}] Here's a minimal app:\n\n"
            "```python\n"
            "from flask import Flask\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/')\n"
            "def hello():\n"
            "    return 'Hello, World!'\n"
            "```\n\n"
            "Run it with `flask run`."
        ),
    ]
    session_input_tokens = [100, 180, 280]
    session_output_tokens = [50, 40, 90]

    for i in range(3):
        trace_id = random_uuid()
        gen_id = random_uuid()
        offset = i * 10.0

        capture_event("$ai_trace", {
            "$ai_trace_id": trace_id,
            "$ai_span_id": trace_id,
            "$ai_session_id": session_id,
            "$ai_trace_name": f"{label}-session-trace-{i}",
            "$ai_span_name": f"{label}-session-trace-{i}",
        }, timestamp=ts(base, offset))

        capture_event("$ai_generation", {
            "$ai_trace_id": trace_id,
            "$ai_span_id": gen_id,
            "$ai_parent_id": trace_id,
            "$ai_session_id": session_id,
            "$ai_span_name": f"step-{i}",
            "$ai_model": "gpt-4o",
            "$ai_provider": "openai",
            "$ai_latency": 1.0,
            "$ai_input_tokens": session_input_tokens[i],
            "$ai_output_tokens": session_output_tokens[i],
            "$ai_http_status": 200,
            "$ai_base_url": "https://api.openai.com/v1",
            "$ai_input": session_messages[i],
            "$ai_output_choices": output_choices(session_outputs[i]),
        }, timestamp=ts(base, offset + 1.0))

        trace_ids.append(trace_id)

    return {"scenario": "session-3-traces", "session_id": session_id, "trace_ids": trace_ids}


def scenario_evaluation(label: str, base: datetime, session_id: str) -> dict:
    """9. Standalone generation + evaluation event."""
    trace_id = random_uuid()
    gen_id = random_uuid()
    eval_id = random_uuid()
    evaluation_config_id = random_uuid()

    capture_event("$ai_generation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-eval-target-completion",
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_latency": 1.5,
        "$ai_input_tokens": 200,
        "$ai_output_tokens": 100,
        "$ai_http_status": 200,
        "$ai_base_url": "https://api.openai.com/v1",
        "$ai_input": [{"role": "user", "content": f"[{label}] Summarize this document."}],
        "$ai_output_choices": output_choices(f"[{label}] This document describes the quarterly results..."),
    }, timestamp=ts(base, 1.5))

    capture_event("$ai_evaluation", {
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_span_name": f"{label}-quality-check",
        "$ai_evaluation_id": evaluation_config_id,
        "$ai_evaluation_result": "true",
        "$ai_evaluation_reasoning": f"[{label}] The summary accurately captures the key points.",
        "$ai_target_event_id": gen_id,
    }, timestamp=ts(base, 2.0))

    return {
        "scenario": "evaluation",
        "trace_id": trace_id,
        "gen_id": gen_id,
        "evaluation_config_id": evaluation_config_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate test data for ai_events migration")
    parser.add_argument(
        "--batch-label",
        required=True,
        help="Label to tag events (e.g. S1, S2, S3) for identifying migration state",
    )
    args = parser.parse_args()

    label = args.batch_label
    now = datetime.now(timezone.utc)
    session_id = f"{label}-test-session"

    print(f"Generating ai_events migration test data with batch label: {label}")
    print(f"  Host: {POSTHOG_HOST}")
    print(f"  Distinct ID: {DISTINCT_ID}")
    print()

    results: list[dict] = []

    # Scenario 1: Simple generation (standalone, no $ai_trace)
    print("1/9  Simple generation...")
    r = scenario_simple_generation(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 2: Nested trace (agentic framework pattern)
    print("2/9  Nested trace...")
    r = scenario_nested_trace(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 3: Tools generation (standalone, no $ai_trace)
    print("3/9  Tools generation...")
    r = scenario_tools_generation(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 4: Error generation (standalone, no $ai_trace)
    print("4/9  Error generation...")
    r = scenario_error_generation(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 5: Heavy properties generation (standalone, no $ai_trace)
    print("5/9  Heavy properties generation...")
    r = scenario_heavy_props_generation(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 6: Embedding (standalone, no $ai_trace)
    print("6/9  Embedding...")
    r = scenario_embedding(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 7: Multi-provider (standalone generations, no $ai_trace)
    print("7/9  Multi-provider...")
    r = scenario_multi_provider(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    # Scenario 8: Session with 3 traces
    print("8/9  Session with 3 traces...")
    r = scenario_session_with_traces(label, now)
    results.append(r)
    print(f"     session_id={r['session_id']}")

    # Scenario 9: Evaluation
    print("9/9  Evaluation event...")
    r = scenario_evaluation(label, now, session_id)
    results.append(r)
    print(f"     trace_id={r['trace_id']}")

    print()
    print("=" * 70)
    print(f"  Batch: {label}")
    print(f"  Session: {session_id}")
    print()
    print(f"  {'Scenario':<25} {'Trace ID'}")
    print(f"  {'-' * 25} {'-' * 36}")
    for r in results:
        tid = r.get("trace_id") or r.get("session_id", "")
        print(f"  {r['scenario']:<25} {tid}")
    print()
    print(f"  Events should appear after ClickHouse processes them (a few seconds).")
    print(f"  Navigate to: {POSTHOG_HOST}/project/llm-analytics")
    print(f"  Search for trace names starting with '{label}-' to find these events.")
    print("=" * 70)


if __name__ == "__main__":
    main()
