#!/usr/bin/env python3
"""
Ingest a trace JSON file into local PostHog for testing.

Usage:
    ./ingest_trace.sh [path/to/trace.json]
    # Or via make:
    make ingest-trace [FILE=path/to/trace.json]

If no path is provided, defaults to example.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import posthog
except ImportError:
    print("\n❌ Error: posthog-python not installed")
    print("\nPlease use the wrapper script:")
    print("  ./ingest_trace.sh")
    print("\nOr via make:")
    print("  make ingest-trace")
    sys.exit(1)

# Load .env file if it exists
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)


def ingest_trace(trace_data: dict, posthog_host: str = None, project_api_key: str = None):
    """
    Ingest a trace and its events into PostHog.

    Args:
        trace_data: The trace JSON object
        posthog_host: PostHog instance URL (reads from POSTHOG_HOST env var if not provided)
        project_api_key: Project API key (reads from POSTHOG_API_KEY env var if not provided)
    """
    # Get host from environment if not provided
    if posthog_host is None:
        posthog_host = os.environ.get("POSTHOG_HOST", "http://localhost:8000")

    # Get API key from environment if not provided
    if project_api_key is None:
        project_api_key = os.environ.get("POSTHOG_API_KEY")
        if not project_api_key:
            print("\n❌ Error: No API key found")
            print("\nPlease set POSTHOG_API_KEY in .env file")
            sys.exit(1)

    # Initialize PostHog client
    posthog.api_key = project_api_key
    posthog.project_api_key = project_api_key
    posthog.host = posthog_host
    posthog.debug = True

    # Get person info
    person = trace_data.get("person", {})
    distinct_id = person.get("distinct_id", "test-user-trace-ingest")

    # Process each event in the trace
    events = trace_data.get("events", [])

    print(f"\n📦 Ingesting trace: {trace_data.get('id', 'unknown')}")
    print(f"👤 Distinct ID: {distinct_id}")
    print(f"📝 Events to ingest: {len(events)}\n")

    for i, event in enumerate(events, 1):
        event_name = event.get("event")
        event_id = event.get("id")
        properties = event.get("properties", {})

        print(f"  [{i}/{len(events)}] Capturing {event_name} (ID: {event_id[:16]}...)")

        # Capture the event with current timestamp
        posthog.capture(
            distinct_id=distinct_id,
            event=event_name,
            properties=properties,
        )

    # Flush to ensure all events are sent
    posthog.flush()

    print(f"\n✅ Successfully ingested {len(events)} events!")
    print(f"🔗 View in PostHog: {posthog_host}/project/1/llm-analytics/traces/{trace_data.get('id')}\n")


def main():
    # Get file path from args or use default
    if len(sys.argv) > 1:
        trace_file = Path(sys.argv[1])
    else:
        trace_file = Path(__file__).parent / "example.json"

    if not trace_file.exists():
        print(f"❌ Error: File not found: {trace_file}")
        print(f"\nUsage: {sys.argv[0]} [path/to/trace.json]")
        sys.exit(1)

    # Load the trace JSON
    print(f"\n📂 Loading trace from: {trace_file}")
    with open(trace_file) as f:
        trace_data = json.load(f)

    # Ingest the trace
    ingest_trace(trace_data)


if __name__ == "__main__":
    main()
