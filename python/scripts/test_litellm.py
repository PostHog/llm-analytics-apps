#!/usr/bin/env python3
"""
Simple test script to verify LiteLLM trace_id -> PostHog $ai_trace_id mapping.

Makes real LiteLLM calls with different trace_id approaches, then check PostHog
to see which property ($ai_trace_id or custom) receives the value.

Usage:
    python test_litellm.py
"""

import os
import sys
import uuid
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path, override=True)

# Set up PostHog env vars BEFORE importing litellm (which initializes PostHog integration)
posthog_host = os.getenv("POSTHOG_HOST", "https://us.posthog.com")
# Convert us.posthog.com -> us.i.posthog.com for LiteLLM's batch API
if "posthog.com" in posthog_host and ".i." not in posthog_host:
    posthog_host = posthog_host.replace("://us.", "://us.i.").replace("://eu.", "://eu.i.")
os.environ["POSTHOG_API_KEY"] = os.getenv("POSTHOG_API_KEY")
os.environ["POSTHOG_API_URL"] = posthog_host

# NOW import litellm after env vars are set
import litellm

litellm.success_callback = ["posthog"]
litellm.failure_callback = ["posthog"]

print("=" * 80)
print("LiteLLM -> PostHog trace_id Test")
print("=" * 80)
print(f"\nPostHog Host: {os.environ.get('POSTHOG_API_URL')}")
print(f"Distinct ID: {os.getenv('POSTHOG_DISTINCT_ID', 'test-user')}")

# Test 1: metadata["trace_id"]
metadata_trace_id = f"metadata-{uuid.uuid4()}"
print(f"\n[Test 1] metadata['trace_id']: {metadata_trace_id}")

response = litellm.completion(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say 'test1'"}],
    max_tokens=10,
    metadata={
        "trace_id": metadata_trace_id,
        "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "test-user"),
    }
)
print(f"   Response: {response.choices[0].message.content}")

# Test 2: litellm_trace_id parameter
param_trace_id = f"param-{uuid.uuid4()}"
print(f"\n[Test 2] litellm_trace_id: {param_trace_id}")

response = litellm.completion(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say 'test2'"}],
    max_tokens=10,
    litellm_trace_id=param_trace_id,
    metadata={
        "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "test-user"),
    }
)
print(f"   Response: {response.choices[0].message.content}")

# Test 3: litellm_session_id parameter
session_id = f"session-{uuid.uuid4()}"
print(f"\n[Test 3] litellm_session_id: {session_id}")

response = litellm.completion(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say 'test3'"}],
    max_tokens=10,
    litellm_session_id=session_id,
    metadata={
        "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "test-user"),
    }
)
print(f"   Response: {response.choices[0].message.content}")

print("\n" + "=" * 80)
print("Done! Check PostHog for these trace IDs:")
print("=" * 80)
print(f"\n1. metadata['trace_id']:  {metadata_trace_id}")
print(f"   -> Expected: custom 'trace_id' property (NOT $ai_trace_id)")
print(f"\n2. litellm_trace_id:      {param_trace_id}")
print(f"   -> Expected: $ai_trace_id")
print(f"\n3. litellm_session_id:    {session_id}")
print(f"   -> Expected: $ai_trace_id")
print()
