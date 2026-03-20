#!/usr/bin/env python3
"""
Generate dummy $ai_generation events with many tool calls for testing
the tools column overflow UI.

Creates events directly via the PostHog capture API — no LLM calls needed.

Usage:
    cd /path/to/llm-analytics-apps
    source python/venv/bin/activate
    python python/scripts/generate_many_tools_test_data.py
"""

import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8010")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
DISTINCT_ID = "tools-overflow-test-user"

if not POSTHOG_API_KEY:
    print("Error: POSTHOG_API_KEY not set. Check your .env file.")
    sys.exit(1)


def capture_event(event: str, properties: dict) -> None:
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{POSTHOG_HOST}/capture/",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        resp.read()


TOOL_NAMES = [
    "get_weather",
    "search_docs",
    "send_email",
    "create_ticket",
    "query_database",
    "translate_text",
    "summarize_article",
    "calculate_price",
    "check_inventory",
    "validate_address",
    "fetch_user_profile",
    "generate_report",
    "schedule_meeting",
    "upload_file",
    "analyze_sentiment",
]


def make_output_choices(tool_names: list[str]) -> str:
    """Build OpenAI Chat format $ai_output_choices with tool calls."""
    tool_calls = [
        {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps({"input": f"test_{name}"}),
            },
        }
        for name in tool_names
    ]
    return json.dumps([{"role": "assistant", "tool_calls": tool_calls}])


# Test scenarios: (description, number of tools)
SCENARIOS = [
    ("3 tools (under limit)", 3),
    ("5 tools (at limit)", 5),
    ("7 tools (slightly over)", 7),
    ("10 tools (well over)", 10),
    ("15 tools (stress test)", 15),
]

session_id = f"tools-test-{uuid.uuid4().hex[:8]}"
trace_id_base = uuid.uuid4().hex[:8]

print(f"Sending {len(SCENARIOS)} test events to {POSTHOG_HOST}")
print(f"Session: {session_id}\n")

for i, (desc, num_tools) in enumerate(SCENARIOS):
    tools = TOOL_NAMES[:num_tools]
    trace_id = f"{trace_id_base}-{i}"

    props = {
        "$ai_model": "gpt-4o",
        "$ai_provider": "openai",
        "$ai_trace_id": trace_id,
        "$ai_session_id": session_id,
        "$ai_input_tokens": 500,
        "$ai_output_tokens": 200,
        "$ai_latency": 1.5,
        "$ai_output_choices": make_output_choices(tools),
    }

    capture_event("$ai_generation", props)
    print(f"  [{i+1}/{len(SCENARIOS)}] {desc}: {', '.join(tools)}")

print(f"\nDone! Sent {len(SCENARIOS)} events with varying tool counts.")
print("Check the traces view to see the tools column overflow behavior.")
