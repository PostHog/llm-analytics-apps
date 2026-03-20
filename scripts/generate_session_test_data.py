#!/usr/bin/env python3
"""
Generate dummy LLM Analytics session data for testing session bugs.

Creates events directly via the PostHog capture API — no LLM calls needed.

Test scenarios:
1. A session with >100 traces (tests "load more" pagination on session detail)
2. A session with nested spans (tests latency calculation — should NOT double-count)
3. A short session (control group for comparing list vs detail values)

Usage:
    cd /path/to/llm-analytics-apps
    source python/venv/bin/activate
    python python/scripts/generate_session_test_data.py

Uses .env file for POSTHOG_API_KEY and POSTHOG_HOST.
"""

import json
import os
import random
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8010")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
DISTINCT_ID = os.getenv("POSTHOG_DISTINCT_ID", "session-bug-test-user")

if not POSTHOG_API_KEY:
    print("Error: POSTHOG_API_KEY not set. Check your .env file.")
    sys.exit(1)


def capture_event(event: str, properties: dict, timestamp: str | None = None) -> None:
    payload = {
        "api_key": POSTHOG_API_KEY,
        "event": event,
        "properties": {
            "$lib": "posthog-python",
            "$lib_version": "0.0.0-test",
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


def make_timestamp(base: datetime, offset_seconds: float) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def generate_trace(
    session_id: str,
    trace_id: str,
    base_time: datetime,
    num_generations: int = 2,
    has_nested_spans: bool = False,
    has_error: bool = False,
) -> float:
    """Generate a single trace with its events. Returns total offset seconds used."""
    offset = 0.0

    # $ai_trace event (the envelope)
    capture_event(
        "$ai_trace",
        {
            "$ai_trace_id": trace_id,
            "$ai_session_id": session_id,
            "$ai_span_id": trace_id,
            "$ai_span_name": f"trace-{trace_id[:8]}",
            "$ai_input_state": json.dumps({"messages": [{"role": "user", "content": "Hello"}]}),
            "$ai_output_state": json.dumps({"messages": [{"role": "assistant", "content": "Hi there!"}]}),
        },
        timestamp=make_timestamp(base_time, offset),
    )

    if has_nested_spans:
        # Create a parent span that wraps child generations
        # This tests that latency doesn't double-count: parent=2s contains child1=0.8s + child2=0.9s
        parent_span_id = str(uuid.uuid4())
        parent_latency = round(random.uniform(1.5, 3.0), 2)
        offset += 0.1

        capture_event(
            "$ai_span",
            {
                "$ai_trace_id": trace_id,
                "$ai_session_id": session_id,
                "$ai_span_id": parent_span_id,
                "$ai_parent_id": trace_id,
                "$ai_span_name": "agent-chain",
                "$ai_latency": str(parent_latency),
            },
            timestamp=make_timestamp(base_time, offset),
        )

        for i in range(num_generations):
            gen_id = str(uuid.uuid4())
            latency = round(random.uniform(0.3, 1.0), 2)
            input_tokens = random.randint(50, 500)
            output_tokens = random.randint(20, 300)
            cost = round((input_tokens * 0.000003) + (output_tokens * 0.000015), 6)
            offset += latency

            props = {
                "$ai_trace_id": trace_id,
                "$ai_session_id": session_id,
                "$ai_span_id": gen_id,
                "$ai_generation_id": gen_id,
                "$ai_parent_id": parent_span_id,  # nested under span, NOT trace root
                "$ai_model": "gpt-4o-mini",
                "$ai_provider": "openai",
                "$ai_latency": str(latency),
                "$ai_input_tokens": str(input_tokens),
                "$ai_output_tokens": str(output_tokens),
                "$ai_input_cost_usd": str(round(input_tokens * 0.000003, 6)),
                "$ai_output_cost_usd": str(round(output_tokens * 0.000015, 6)),
                "$ai_total_cost_usd": str(cost),
            }
            if has_error and i == num_generations - 1:
                props["$ai_is_error"] = "true"
                props["$ai_error"] = "Rate limit exceeded"

            capture_event("$ai_generation", props, timestamp=make_timestamp(base_time, offset))

        # The correct latency for this trace should be parent_latency (direct child of root),
        # NOT parent_latency + sum(child latencies)
        return offset + 0.5
    else:
        # Flat trace: generations are direct children of the trace root
        for i in range(num_generations):
            gen_id = str(uuid.uuid4())
            latency = round(random.uniform(0.2, 0.8), 2)
            input_tokens = random.randint(50, 300)
            output_tokens = random.randint(20, 200)
            cost = round((input_tokens * 0.000003) + (output_tokens * 0.000015), 6)
            offset += latency

            props = {
                "$ai_trace_id": trace_id,
                "$ai_session_id": session_id,
                "$ai_span_id": gen_id,
                "$ai_generation_id": gen_id,
                "$ai_parent_id": trace_id,  # direct child of trace root
                "$ai_model": "gpt-4o-mini",
                "$ai_provider": "openai",
                "$ai_latency": str(latency),
                "$ai_input_tokens": str(input_tokens),
                "$ai_output_tokens": str(output_tokens),
                "$ai_input_cost_usd": str(round(input_tokens * 0.000003, 6)),
                "$ai_output_cost_usd": str(round(output_tokens * 0.000015, 6)),
                "$ai_total_cost_usd": str(cost),
            }
            if has_error and i == num_generations - 1:
                props["$ai_is_error"] = "true"

            capture_event("$ai_generation", props, timestamp=make_timestamp(base_time, offset))

        return offset + 0.5


def main() -> None:
    now = datetime.now(timezone.utc)

    # Scenario 1: Session with 120 traces (tests pagination — default limit is 100)
    session_1 = f"test-pagination-{uuid.uuid4().hex[:8]}"
    print(f"Scenario 1: Creating session with 120 traces: {session_1}")
    base = now - timedelta(hours=2)
    offset = 0.0
    for i in range(120):
        trace_id = str(uuid.uuid4())
        elapsed = generate_trace(
            session_id=session_1,
            trace_id=trace_id,
            base_time=base + timedelta(seconds=offset),
            num_generations=1,
        )
        offset += elapsed
        if (i + 1) % 20 == 0:
            print(f"  ...created {i + 1}/120 traces")
    print(f"  Done. Session ID: {session_1}")

    # Scenario 2: Session with nested spans (tests latency calculation)
    session_2 = f"test-latency-{uuid.uuid4().hex[:8]}"
    print(f"\nScenario 2: Creating session with 5 nested-span traces: {session_2}")
    base = now - timedelta(hours=1)
    offset = 0.0
    for i in range(5):
        trace_id = str(uuid.uuid4())
        elapsed = generate_trace(
            session_id=session_2,
            trace_id=trace_id,
            base_time=base + timedelta(seconds=offset),
            num_generations=3,
            has_nested_spans=True,
            has_error=(i == 2),
        )
        offset += elapsed
    print(f"  Done. Session ID: {session_2}")

    # Scenario 3: Short control session (3 flat traces)
    session_3 = f"test-control-{uuid.uuid4().hex[:8]}"
    print(f"\nScenario 3: Creating control session with 3 flat traces: {session_3}")
    base = now - timedelta(minutes=30)
    offset = 0.0
    for i in range(3):
        trace_id = str(uuid.uuid4())
        elapsed = generate_trace(
            session_id=session_3,
            trace_id=trace_id,
            base_time=base + timedelta(seconds=offset),
            num_generations=2,
        )
        offset += elapsed
    print(f"  Done. Session ID: {session_3}")

    print("\n--- Summary ---")
    print(f"Pagination test:  {session_1}  (120 traces, expect 'Load more' button)")
    print(f"Latency test:     {session_2}  (5 traces with nested spans, check latency consistency)")
    print(f"Control session:  {session_3}  (3 flat traces, baseline comparison)")
    print(f"\nEvents will appear after ClickHouse processes them (usually a few seconds).")
    print(f"Navigate to: {POSTHOG_HOST}/project/llm-analytics/sessions")


if __name__ == "__main__":
    main()
