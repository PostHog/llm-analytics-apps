#!/usr/bin/env python3
"""
Send test $ai_generation events through PostHog to verify cost calculation behavior.

Three test cases:
1. "correct" - exclusive $ai_input_tokens (2851), no $ai_total_tokens
2. "customer" - inclusive $ai_input_tokens (48268), with $ai_total_tokens (48864)
3. "no_total" - inclusive $ai_input_tokens (48268), WITHOUT $ai_total_tokens

Then query the PostHog API to compare stored costs.

Usage:
    cd python && python scripts/debug-anthropic-cache-cost/test_local_pipeline.py

Requires .env at the repo root with:
    POSTHOG_API_KEY=phc_...        # Project API key (for sending events)
    POSTHOG_HOST=http://localhost:8010
    POSTHOG_PERSONAL_API_KEY=phx_... # Personal API key (for querying events)
"""

import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env"))

import requests

POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8010")
API_TOKEN = os.getenv("POSTHOG_API_KEY")
PERSONAL_API_KEY = os.getenv("POSTHOG_PERSONAL_API_KEY")

if not API_TOKEN:
    print("ERROR: POSTHOG_API_KEY not set in .env")
    sys.exit(1)

if not PERSONAL_API_KEY:
    print("ERROR: POSTHOG_PERSONAL_API_KEY not set in .env")
    print("Create one at: {}/settings/user-api-keys".format(POSTHOG_HOST))
    sys.exit(1)

# Values from the customer's actual event
CACHE_READ = 45417
EXCLUSIVE_INPUT = 2851  # 48268 - 45417
INCLUSIVE_INPUT = 48268  # what the customer has
OUTPUT_TOKENS = 596
TOTAL_TOKENS = 48864  # 48268 + 596


def make_event(test_name: str, input_tokens: int, output_tokens: int, extra_props: dict | None = None) -> dict:
    # Use a unique run_id so we can find events from this specific run
    return {
        "event": "$ai_generation",
        "distinct_id": f"cost-debug-{test_name}",
        "properties": {
            "$ai_provider": "anthropic",
            "$ai_model": "claude-haiku-4-5",
            "$ai_input_tokens": input_tokens,
            "$ai_output_tokens": output_tokens,
            "$ai_cache_read_input_tokens": CACHE_READ,
            "$ai_trace_id": str(uuid.uuid4()),
            "$ai_span_id": str(uuid.uuid4()),
            "test_name": test_name,
            "test_run_id": RUN_ID,
            **(extra_props or {}),
        },
    }


def send_event(event: dict):
    resp = requests.post(
        f"{POSTHOG_HOST}/e/",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"api_key": API_TOKEN, **event}),
    )
    print(f"  Sent '{event['properties']['test_name']}': {resp.status_code}")
    return resp


def query_events(test_names: list[str], max_retries: int = 15, delay: float = 3.0) -> dict:
    """Query PostHog API to check stored event properties."""
    found = {}
    for attempt in range(max_retries):
        time.sleep(delay)
        print(f"  Querying for events (attempt {attempt + 1}/{max_retries})...")

        resp = requests.get(
            f"{POSTHOG_HOST}/api/projects/1/events/",
            params={"event": "$ai_generation", "limit": 20, "orderBy": '["-timestamp"]'},
            headers={"Authorization": f"Bearer {PERSONAL_API_KEY}"},
        )

        if resp.status_code != 200:
            print(f"  API returned {resp.status_code}: {resp.text[:200]}")
            continue

        data = resp.json()
        events = data.get("results", [])

        for ev in events:
            props = ev.get("properties", {})
            name = props.get("test_name")
            run_id = props.get("test_run_id")
            if name in test_names and run_id == RUN_ID:
                found[name] = props

        if len(found) == len(test_names):
            return found

        print(f"  Found {len(found)}/{len(test_names)} test events so far...")

    return found


def print_comparison(results: dict):
    print("\n" + "=" * 90)
    print("  RESULTS COMPARISON")
    print("=" * 90)

    fields = [
        "$ai_input_tokens",
        "$ai_output_tokens",
        "$ai_cache_read_input_tokens",
        "$ai_total_tokens",
        "$ai_input_cost_usd",
        "$ai_output_cost_usd",
        "$ai_total_cost_usd",
        "$ai_cost_model_source",
        "$ai_cost_model_provider",
        "$ai_model_cost_used",
    ]

    # Header
    names = list(results.keys())
    header = f"  {'Field':<35}" + "".join(f"{n:<25}" for n in names)
    print(header)
    print("  " + "-" * (35 + 25 * len(names)))

    for field in fields:
        row = f"  {field:<35}"
        for name in names:
            val = results[name].get(field, "NOT SET")
            if isinstance(val, float):
                row += f"${val:<24.7f}"
            else:
                row += f"{str(val):<25}"
        print(row)

    # Analysis
    print("\n" + "=" * 90)
    print("  ANALYSIS")
    print("=" * 90)

    if "correct" in results:
        props = results["correct"]
        actual_input_cost = props.get("$ai_input_cost_usd", 0)
        print(f"\n  Test 'correct' (exclusive input={EXCLUSIVE_INPUT}):")
        print(f"    $ai_input_cost_usd:  {actual_input_cost}")
        print(f"    This should reflect cost for {EXCLUSIVE_INPUT} uncached + {CACHE_READ} cached tokens")

    if "customer" in results:
        props = results["customer"]
        actual_input_cost = props.get("$ai_input_cost_usd", 0)
        print(f"\n  Test 'customer' (inclusive input={INCLUSIVE_INPUT}, with $ai_total_tokens={TOTAL_TOKENS}):")
        print(f"    $ai_input_cost_usd:  {actual_input_cost}")
        print(f"    Customer sees:       0.0528097")
        if actual_input_cost:
            print(f"    Match: {abs(actual_input_cost - 0.0528097) < 0.001}")

    if "correct" in results and "customer" in results:
        correct_cost = results["correct"].get("$ai_input_cost_usd", 0)
        customer_cost = results["customer"].get("$ai_input_cost_usd", 0)
        if correct_cost and correct_cost > 0:
            print(f"\n  OVERCHARGE FACTOR: {customer_cost / correct_cost:.1f}x")

    if "no_total" in results:
        props = results["no_total"]
        total_tokens = props.get("$ai_total_tokens", "NOT SET")
        print(f"\n  Test 'no_total' (inclusive input={INCLUSIVE_INPUT}, NO $ai_total_tokens sent):")
        print(f"    $ai_total_tokens after pipeline: {total_tokens}")
        if total_tokens != "NOT SET":
            print(f"    => PIPELINE CREATED $ai_total_tokens! Value: {total_tokens}")
        else:
            print(f"    => Pipeline did NOT create $ai_total_tokens (as expected)")
            print(f"    => Confirms $ai_total_tokens in customer event must come from client side")


# Generate a unique run ID so we only find events from this run
RUN_ID = str(uuid.uuid4())[:8]


def main():
    print("=" * 90)
    print("  Local Pipeline Cost Calculation Test")
    print("  Reproducing customer's Anthropic cache token cost issue")
    print(f"  Run ID: {RUN_ID}")
    print(f"  PostHog: {POSTHOG_HOST}")
    print("=" * 90)

    test_names = ["correct", "customer", "no_total"]

    # Build and send events
    events = [
        make_event("correct", EXCLUSIVE_INPUT, OUTPUT_TOKENS),
        make_event("customer", INCLUSIVE_INPUT, OUTPUT_TOKENS, {"$ai_total_tokens": TOTAL_TOKENS}),
        make_event("no_total", INCLUSIVE_INPUT, OUTPUT_TOKENS),
    ]

    print("\nSending test events...")
    for ev in events:
        send_event(ev)

    print("\nWaiting for events to be processed...")
    results = query_events(test_names)

    if not results:
        print("\n  ERROR: No test events found after waiting.")
        print("  Check that PostHog is processing events and the API keys are correct.")
        return

    if len(results) < len(test_names):
        missing = set(test_names) - set(results.keys())
        print(f"\n  WARNING: Missing events: {missing}")
        print("  Showing results for what we found...")

    print_comparison(results)


if __name__ == "__main__":
    main()
