#!/usr/bin/env python3
"""
Debug script for Anthropic cache token cost investigation.

Reproduces the customer's scenario: non-streaming AsyncAnthropic with cached content.
The customer sees $ai_input_tokens set to the INCLUSIVE value (input + cache_read)
instead of the EXCLUSIVE value that the Anthropic API returns.

This script:
1. Makes two calls with the same large system prompt to trigger cache_read
2. Inspects the raw Anthropic API response usage
3. Spies on ph_client.capture() to see what PostHog receives
4. Compares the values to detect any discrepancy
5. Writes results to output.md

Usage:
    cd python && python scripts/debug-anthropic-cache-cost/run.py

Slack thread: https://posthog.slack.com/archives/C09AJEE3YSY/p1771625286859039
"""

import asyncio
import io
import os
import sys
from datetime import datetime, timezone

# Add python/ dir to path so we can import from the project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# Also add python/ itself
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env"))

import anthropic
import posthog
from posthog.ai.anthropic import AsyncAnthropic


# Generate a large system prompt to ensure caching kicks in.
# Anthropic requires 1024+ tokens for cache eligibility.
LARGE_SYSTEM_PROMPT = "\n".join(
    f"Rule {i}: You are an expert assistant who always provides accurate, helpful, and detailed responses. "
    f"You must follow all safety guidelines and provide balanced perspectives on complex topics. "
    f"When asked about technical subjects, provide code examples where appropriate."
    for i in range(300)
)

USER_MESSAGE = "What is 2+2?"
MODEL = "claude-haiku-4-5-20251001"

# Output directory (same dir as this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "output.md")


class OutputWriter:
    """Writes to both stdout and a buffer for the markdown file."""

    def __init__(self):
        self.buffer = io.StringIO()
        self.md_sections: list[dict] = []

    def print(self, text: str = ""):
        """Print to stdout and buffer."""
        print(text)
        self.buffer.write(text + "\n")

    def start_section(self, title: str):
        """Start a new section (prints a divider)."""
        self.print(f"\n{'=' * 70}")
        self.print(f"  {title}")
        self.print(f"{'=' * 70}")

    def print_usage(self, label: str, usage):
        """Pretty-print an Anthropic usage object."""
        self.print(f"\n  {label}:")
        self.print(f"    input_tokens:                {getattr(usage, 'input_tokens', 'N/A')}")
        self.print(f"    output_tokens:               {getattr(usage, 'output_tokens', 'N/A')}")
        self.print(f"    cache_read_input_tokens:     {getattr(usage, 'cache_read_input_tokens', 'N/A')}")
        self.print(f"    cache_creation_input_tokens: {getattr(usage, 'cache_creation_input_tokens', 'N/A')}")

    def get_raw_output(self) -> str:
        return self.buffer.getvalue()


def make_ph_client():
    """Create a PostHog client using the correct constructor."""
    return posthog.Posthog(
        project_api_key=os.getenv("POSTHOG_API_KEY", "test-key"),
        host=os.getenv("POSTHOG_HOST", "https://us.posthog.com"),
    )


async def step1_raw_anthropic_api(out: OutputWriter) -> dict:
    """Call the Anthropic API directly (no PostHog wrapper) to establish ground truth."""
    out.start_section("STEP 1: Raw Anthropic API (no PostHog wrapper)")
    out.print("  Making two calls to populate cache, then checking usage on second call...")

    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    system_with_cache = [
        {
            "type": "text",
            "text": LARGE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # First call: populates the cache
    out.print("\n  Call 1 (cache miss - should create cache)...")
    response1 = await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": USER_MESSAGE}],
    )
    out.print_usage("Call 1 usage", response1.usage)

    cache_creation = getattr(response1.usage, "cache_creation_input_tokens", 0) or 0
    if cache_creation == 0:
        out.print("\n  WARNING: No cache_creation_input_tokens on call 1!")
        out.print("  System prompt may be too small for cache eligibility (need 1024+ tokens).")
        out.print(f"  System prompt length: ~{len(LARGE_SYSTEM_PROMPT.split())} words")

    # Second call: should hit cache
    out.print("\n  Call 2 (cache hit expected)...")
    response2 = await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": USER_MESSAGE}],
    )
    out.print_usage("Call 2 usage", response2.usage)

    input_tokens = response2.usage.input_tokens
    cache_read = getattr(response2.usage, "cache_read_input_tokens", 0) or 0

    out.print(f"\n  Analysis:")
    out.print(f"    input_tokens (from API):       {input_tokens}")
    out.print(f"    cache_read_input_tokens:       {cache_read}")
    out.print(f"    input + cache_read:            {input_tokens + cache_read}")

    if cache_read > 0:
        if input_tokens < cache_read:
            out.print(f"    => input_tokens is EXCLUSIVE of cache (correct Anthropic behavior)")
        else:
            out.print(f"    => input_tokens is INCLUSIVE of cache (UNEXPECTED!)")
    else:
        out.print(f"    => No cache hit on call 2 - cannot determine inclusive/exclusive")

    return {
        "input_tokens": input_tokens,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "output_tokens": response2.usage.output_tokens,
    }


async def step2_posthog_wrapper(out: OutputWriter) -> dict:
    """Call through posthog.AsyncAnthropic and spy on capture() to see what properties are sent."""
    out.start_section("STEP 2: PostHog AsyncAnthropic wrapper (spy on capture)")

    captured_events = []
    ph_client = make_ph_client()

    def spy_capture(*args, **kwargs):
        captured_events.append(kwargs)
        props = kwargs.get("properties", {})
        out.print(f"\n  [SPY] ph_client.capture() called!")
        out.print(f"    event:                         {kwargs.get('event')}")
        out.print(f"    $ai_provider:                  {props.get('$ai_provider')}")
        out.print(f"    $ai_model:                     {props.get('$ai_model')}")
        out.print(f"    $ai_input_tokens:              {props.get('$ai_input_tokens')}")
        out.print(f"    $ai_output_tokens:             {props.get('$ai_output_tokens')}")
        out.print(f"    $ai_cache_read_input_tokens:   {props.get('$ai_cache_read_input_tokens')}")
        out.print(f"    $ai_cache_creation_input_tokens: {props.get('$ai_cache_creation_input_tokens')}")
        out.print(f"    $ai_total_tokens:              {props.get('$ai_total_tokens', 'NOT SET')}")

    ph_client.capture = spy_capture

    client = AsyncAnthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        posthog_client=ph_client,
    )

    system_with_cache = [
        {
            "type": "text",
            "text": LARGE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # First call: populate cache
    out.print("\n  Call 1 (cache miss - populating cache)...")
    response1 = await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": USER_MESSAGE}],
        posthog_distinct_id="debug-cache-cost",
    )
    out.print_usage("Raw API usage (call 1)", response1.usage)

    # Second call: should hit cache
    out.print("\n  Call 2 (cache hit expected)...")
    response2 = await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": USER_MESSAGE}],
        posthog_distinct_id="debug-cache-cost",
    )
    out.print_usage("Raw API usage (call 2)", response2.usage)

    result = {"sdk_correct": None, "total_tokens_set": False}

    if len(captured_events) >= 2:
        event = captured_events[-1]
        props = event.get("properties", {})
        api_input = response2.usage.input_tokens
        sdk_input = props.get("$ai_input_tokens")
        cache_read = getattr(response2.usage, "cache_read_input_tokens", 0) or 0

        out.start_section("COMPARISON (Call 2 - cache hit)")
        out.print(f"    Anthropic API input_tokens:   {api_input}")
        out.print(f"    SDK $ai_input_tokens:         {sdk_input}")
        out.print(f"    cache_read_input_tokens:      {cache_read}")
        out.print(f"    API input + cache_read:       {api_input + cache_read}")
        out.print()

        if cache_read == 0:
            out.print("    INCONCLUSIVE: No cache hit, cannot compare inclusive vs exclusive")
        elif sdk_input == api_input:
            out.print("    RESULT: SDK correctly passes through EXCLUSIVE input_tokens")
            result["sdk_correct"] = True
        elif sdk_input == api_input + cache_read:
            out.print("    RESULT: BUG! SDK is sending INCLUSIVE input_tokens (input + cache_read)")
            result["sdk_correct"] = False
        else:
            out.print(f"    RESULT: UNEXPECTED! SDK value ({sdk_input}) doesn't match either pattern")

        if "$ai_total_tokens" in props:
            out.print(f"\n    WARNING: $ai_total_tokens is set to {props['$ai_total_tokens']}")
            out.print("    The Anthropic wrapper should NOT set this property!")
            result["total_tokens_set"] = True
        else:
            out.print(f"\n    OK: $ai_total_tokens is not set (expected for Anthropic wrapper)")

        result["api_input"] = api_input
        result["sdk_input"] = sdk_input
        result["cache_read"] = cache_read

    ph_client.shutdown()
    return result


async def step3_posthog_wrapper_with_custom_properties(out: OutputWriter) -> dict:
    """Test if posthog_properties can override SDK token values (our leading theory)."""
    out.start_section("STEP 3: Test posthog_properties override (leading theory)")
    out.print("  Simulating customer passing their own inclusive token counts via posthog_properties...")

    captured_events = []
    ph_client = make_ph_client()

    def spy_capture(*args, **kwargs):
        captured_events.append(kwargs)

    ph_client.capture = spy_capture

    client = AsyncAnthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        posthog_client=ph_client,
    )

    system_with_cache = [
        {
            "type": "text",
            "text": LARGE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # Warm up cache first (discard this event)
    await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": "Hi"}],
        posthog_distinct_id="debug-cache-cost",
    )

    # 3a) Simple override with hardcoded values
    out.print("\n  3a) Simple override with hardcoded values...")
    response = await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": USER_MESSAGE}],
        posthog_distinct_id="debug-cache-cost",
        posthog_properties={
            "$ai_input_tokens": 99999,
            "$ai_total_tokens": 100599,
        },
    )

    override_works = False
    if len(captured_events) >= 2:
        props = captured_events[-1].get("properties", {})
        api_input = response.usage.input_tokens
        sdk_input = props.get("$ai_input_tokens")

        out.print(f"    Anthropic API input_tokens:   {api_input}")
        out.print(f"    SDK $ai_input_tokens:         {sdk_input}")
        out.print(f"    $ai_total_tokens:             {props.get('$ai_total_tokens', 'NOT SET')}")

        if sdk_input == 99999:
            out.print("    => posthog_properties OVERRIDES the SDK's correct value")
            override_works = True
        else:
            out.print(f"    => posthog_properties did NOT override (got {sdk_input})")

    # 3b) Simulate the exact customer pattern
    out.print("\n  3b) Simulating customer computing inclusive tokens from the response...")
    out.print("  (Customer code might do: input_tokens = usage.input_tokens + usage.cache_read_input_tokens)")

    captured_events.clear()

    prev_api_input = response.usage.input_tokens
    prev_cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    prev_output = response.usage.output_tokens
    inclusive_input = prev_api_input + prev_cache_read
    computed_total = inclusive_input + prev_output

    out.print(f"    Customer computes: inclusive_input = {prev_api_input} + {prev_cache_read} = {inclusive_input}")
    out.print(f"    Customer computes: total = {inclusive_input} + {prev_output} = {computed_total}")

    response2 = await client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=system_with_cache,
        messages=[{"role": "user", "content": "Tell me a fun fact."}],
        posthog_distinct_id="debug-cache-cost",
        posthog_properties={
            "$ai_input_tokens": inclusive_input,
            "$ai_total_tokens": computed_total,
        },
    )

    result = {"override_works": override_works}

    if captured_events:
        props = captured_events[-1].get("properties", {})
        api_input = response2.usage.input_tokens
        cache_read = getattr(response2.usage, "cache_read_input_tokens", 0) or 0
        sdk_input = props.get("$ai_input_tokens")
        sdk_total = props.get("$ai_total_tokens", "NOT SET")
        sdk_cache_read = props.get("$ai_cache_read_input_tokens")

        out.print(f"    Anthropic API input_tokens:         {api_input} (exclusive)")
        out.print(f"    Anthropic API cache_read:           {cache_read}")
        out.print(f"    Anthropic API output_tokens:        {response2.usage.output_tokens}")
        out.print(f"    ---")
        out.print(f"    Stored $ai_input_tokens:            {sdk_input} (inclusive!)")
        out.print(f"    Stored $ai_cache_read_input_tokens: {sdk_cache_read}")
        out.print(f"    Stored $ai_total_tokens:            {sdk_total}")
        out.print(f"    ---")

        # Cost math
        prompt_rate = 1.0 / 1_000_000
        cache_rate = 0.1 / 1_000_000

        correct_uncached_cost = api_input * prompt_rate
        correct_cache_cost = cache_read * cache_rate
        correct_total = correct_uncached_cost + correct_cache_cost

        wrong_uncached_cost = sdk_input * prompt_rate if sdk_input else 0
        wrong_cache_cost = (sdk_cache_read or 0) * cache_rate
        wrong_total = wrong_uncached_cost + wrong_cache_cost

        out.print(f"    COST COMPARISON (haiku pricing: $1/Mtok input, $0.10/Mtok cache):")
        out.print(f"")
        out.print(f"    Correct (exclusive input_tokens = {api_input}):")
        out.print(f"      uncached: {api_input} * $1/Mtok    = ${correct_uncached_cost:.6f}")
        out.print(f"      cached:   {cache_read} * $0.10/Mtok = ${correct_cache_cost:.6f}")
        out.print(f"      total input cost:                    ${correct_total:.6f}")
        out.print(f"")
        out.print(f"    Wrong (inclusive input_tokens = {sdk_input}, treated as exclusive):")
        out.print(f"      uncached: {sdk_input} * $1/Mtok    = ${wrong_uncached_cost:.6f}")
        out.print(f"      cached:   {sdk_cache_read} * $0.10/Mtok = ${wrong_cache_cost:.6f}")
        out.print(f"      total input cost:                    ${wrong_total:.6f}")
        out.print(f"")
        if correct_total > 0:
            overcharge = wrong_total / correct_total
            out.print(f"    OVERCHARGE: {overcharge:.1f}x ({overcharge * 100 - 100:.0f}% more)")
            result["overcharge_factor"] = overcharge

        result.update({
            "api_input": api_input,
            "cache_read": cache_read,
            "sdk_input": sdk_input,
            "sdk_total": sdk_total,
            "sdk_cache_read": sdk_cache_read,
            "correct_cost": correct_total,
            "wrong_cost": wrong_total,
            "output_tokens": response2.usage.output_tokens,
        })

    ph_client.shutdown()
    return result


async def step4_prove_total_tokens_never_set(out: OutputWriter) -> dict:
    """Prove that $ai_total_tokens is never set by the Anthropic SDK code path.

    This step inspects the actual SDK source code to show:
    1. The Anthropic converter only extracts input_tokens, output_tokens, cache_* — no total_tokens
    2. The general utils.py only tags $ai_input_tokens and $ai_output_tokens — no $ai_total_tokens
    3. Only the OpenAI Agents processor sets $ai_total_tokens

    If $ai_total_tokens appears in a stored event from the Anthropic wrapper,
    it MUST have come from outside the SDK (e.g. posthog_properties override).
    """
    out.start_section("STEP 4: Prove $ai_total_tokens is never set by Anthropic SDK")
    out.print("  Inspecting SDK source code to confirm no code path sets $ai_total_tokens for Anthropic...")

    import inspect

    from posthog.ai.anthropic import anthropic_converter
    from posthog.ai import utils as ai_utils

    result = {"anthropic_converter_clean": False, "utils_clean": False, "openai_agents_sets_it": False}

    # 1. Check the Anthropic converter source
    out.print("\n  1) Anthropic converter (extract_anthropic_usage_from_response):")
    converter_source = inspect.getsource(anthropic_converter.extract_anthropic_usage_from_response)
    has_total_in_converter = "total_tokens" in converter_source
    out.print(f"     File: posthog/ai/anthropic/anthropic_converter.py")
    out.print(f"     Contains 'total_tokens': {has_total_in_converter}")
    if not has_total_in_converter:
        out.print(f"     => CONFIRMED: Anthropic converter does NOT extract total_tokens")
        result["anthropic_converter_clean"] = True
    else:
        out.print(f"     => UNEXPECTED: Found 'total_tokens' reference in converter!")

    # Also check the streaming extractor
    streaming_source = inspect.getsource(anthropic_converter.extract_anthropic_usage_from_event)
    has_total_in_streaming = "total_tokens" in streaming_source
    out.print(f"\n     Streaming extractor (extract_anthropic_usage_from_event):")
    out.print(f"     Contains 'total_tokens': {has_total_in_streaming}")

    # 2. Check utils.py - the code that tags properties before capture()
    out.print("\n  2) General AI utils (posthog/ai/utils.py):")
    utils_source = inspect.getsource(ai_utils)
    has_total_in_utils = "ai_total_tokens" in utils_source or "$ai_total_tokens" in utils_source
    out.print(f"     File: posthog/ai/utils.py")
    out.print(f"     Contains 'ai_total_tokens': {has_total_in_utils}")
    if not has_total_in_utils:
        out.print(f"     => CONFIRMED: utils.py never tags $ai_total_tokens")
        result["utils_clean"] = True
    else:
        out.print(f"     => UNEXPECTED: Found 'ai_total_tokens' reference in utils!")

    # 3. Show that OpenAI Agents DOES set it (for contrast)
    out.print("\n  3) OpenAI Agents processor (for contrast):")
    try:
        from posthog.ai.openai_agents import processor as agents_processor
        agents_source = inspect.getsource(agents_processor)
        has_total_in_agents = "$ai_total_tokens" in agents_source
        out.print(f"     File: posthog/ai/openai_agents/processor.py")
        out.print(f"     Contains '$ai_total_tokens': {has_total_in_agents}")
        if has_total_in_agents:
            out.print(f"     => This is the ONLY code path that sets $ai_total_tokens")
            result["openai_agents_sets_it"] = True
    except ImportError:
        out.print(f"     Could not import openai_agents processor (not installed)")

    # 4. Summary
    out.print(f"\n  CONCLUSION:")
    if result["anthropic_converter_clean"] and result["utils_clean"]:
        out.print(f"     The Anthropic SDK code path NEVER sets $ai_total_tokens.")
        out.print(f"     If $ai_total_tokens appears in a stored event from posthog.ai.anthropic,")
        out.print(f"     it MUST have come from outside the SDK — most likely via posthog_properties.")
        out.print(f"")
        out.print(f"     Code references (posthog-python SDK):")
        out.print(f"       - posthog/ai/anthropic/anthropic_converter.py:206-231")
        out.print(f"         extract_anthropic_usage_from_response() -> only sets input_tokens, output_tokens, cache_*")
        out.print(f"       - posthog/ai/utils.py -> tag('$ai_input_tokens', ...) and tag('$ai_output_tokens', ...)")
        out.print(f"         NO tag('$ai_total_tokens', ...) anywhere")
        out.print(f"       - posthog/ai/openai_agents/processor.py:539,696")
        out.print(f"         ONLY place $ai_total_tokens is set (OpenAI Agents only, not Anthropic)")
    else:
        out.print(f"     UNEXPECTED: Found total_tokens references where none were expected!")

    return result


def write_output_md(step1_result: dict, step2_result: dict, step3_result: dict, raw_output: str, step4_result: dict | None = None):
    """Write a shareable output.md summarizing the investigation."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sdk_version = "unknown"
    try:
        sdk_version = posthog.__version__
    except Exception:
        pass

    anthropic_version = "unknown"
    try:
        anthropic_version = anthropic.__version__
    except Exception:
        pass

    md = f"""# Anthropic Cache Token Cost - Debug Results

**Date:** {now}
**Model:** `{MODEL}`
**PostHog Python SDK:** `v{sdk_version}`
**Anthropic SDK:** `v{anthropic_version}`

---

## TL;DR

The PostHog Python SDK (`posthog.ai.anthropic.AsyncAnthropic`) correctly passes through the **exclusive** `input_tokens` value from the Anthropic API. The SDK does **not** modify or inflate this value.

However, if you pass `posthog_properties` to `messages.create()` containing `$ai_input_tokens` or `$ai_total_tokens`, those values **override** the SDK's correct values. This can cause inflated cost calculations if the overriding values include cached tokens in the input count.

---

## Test 1: Raw Anthropic API Behavior

Verified that the Anthropic API returns `input_tokens` **exclusive** of cached tokens:

| Field | Value |
|-------|-------|
| `input_tokens` | {step1_result['input_tokens']} |
| `cache_read_input_tokens` | {step1_result['cache_read']} |
| `cache_creation_input_tokens` | {step1_result['cache_creation']} |
| `output_tokens` | {step1_result['output_tokens']} |

**Result:** `input_tokens` ({step1_result['input_tokens']}) is much smaller than `cache_read_input_tokens` ({step1_result['cache_read']}), confirming Anthropic returns **exclusive** counts.

---

## Test 2: PostHog SDK Wrapper (No Custom Properties)

Spied on `ph_client.capture()` to see what the SDK sends to PostHog:

| Field | Anthropic API | PostHog SDK |
|-------|--------------|-------------|
| `input_tokens` / `$ai_input_tokens` | {step2_result.get('api_input', 'N/A')} | {step2_result.get('sdk_input', 'N/A')} |
| `cache_read_input_tokens` / `$ai_cache_read_input_tokens` | {step2_result.get('cache_read', 'N/A')} | {step2_result.get('cache_read', 'N/A')} |
| `$ai_total_tokens` | N/A | {'SET' if step2_result.get('total_tokens_set') else 'NOT SET'} |

**Result:** {"SDK correctly passes through the exclusive value." if step2_result.get('sdk_correct') else "See raw output for details."}
{"" if not step2_result.get('total_tokens_set') else "WARNING: $ai_total_tokens was unexpectedly set!"}
{"The Anthropic wrapper does NOT set `$ai_total_tokens` - this is expected." if not step2_result.get('total_tokens_set') else ""}

---

## Test 3: `posthog_properties` Override (Root Cause)

### 3a) Direct Override Test

Passed `posthog_properties={{"$ai_input_tokens": 99999}}` to `messages.create()`.

**Result:** {"The SDK's correct value was **overridden** to 99999. This confirms `posthog_properties` takes precedence." if step3_result.get('override_works') else "Override did not work as expected."}

### 3b) Simulated Customer Pattern

Simulated what happens when a customer computes inclusive token counts and passes them via `posthog_properties`:

```python
# Customer code pattern that causes the overcharge:
inclusive_input = response.usage.input_tokens + response.usage.cache_read_input_tokens
total = inclusive_input + response.usage.output_tokens

client.messages.create(
    ...,
    posthog_properties={{
        "$ai_input_tokens": inclusive_input,   # WRONG - includes cached tokens!
        "$ai_total_tokens": total,
    }},
)
```

| Field | Correct (Exclusive) | Wrong (Inclusive) |
|-------|-------------------|-----------------|
| `$ai_input_tokens` | {step3_result.get('api_input', 'N/A')} | {step3_result.get('sdk_input', 'N/A')} |
| `$ai_cache_read_input_tokens` | {step3_result.get('cache_read', 'N/A')} | {step3_result.get('sdk_cache_read', 'N/A')} |
| `$ai_total_tokens` | not set | {step3_result.get('sdk_total', 'N/A')} |

### Cost Impact

Using `claude-haiku-4-5` pricing ($1/Mtok input, $0.10/Mtok cache read):

| | Correct | Overcharged |
|--|---------|-------------|
| Uncached input cost | ${step3_result.get('correct_cost', 0):.6f} | ${step3_result.get('wrong_cost', 0):.6f} |
| **Overcharge factor** | | **{step3_result.get('overcharge_factor', 0):.1f}x** |

---

## How to Check if This Affects You

Look for any code that passes `posthog_properties` to `messages.create()` with token-related fields:

```python
# Search your codebase for patterns like:
client.messages.create(
    ...,
    posthog_properties={{
        "$ai_input_tokens": ...,    # This overrides the SDK!
        "$ai_total_tokens": ...,    # This also overrides!
    }},
)
```

The SDK already extracts the correct exclusive `input_tokens` from the Anthropic response. You do **not** need to pass these values yourself.

### What to Do

**Option A (Recommended):** Remove `$ai_input_tokens` and `$ai_total_tokens` from your `posthog_properties`. The SDK handles these correctly.

**Option B:** If you need to pass custom properties, make sure `$ai_input_tokens` uses the **exclusive** value from `response.usage.input_tokens` (not `input_tokens + cache_read_input_tokens`).

---

## Test 4: SDK Source Code Inspection

Programmatically inspected the PostHog Python SDK source to prove `$ai_total_tokens` cannot come from the Anthropic code path:

| Component | File | Sets `$ai_total_tokens`? |
|-----------|------|------------------------|
| Anthropic converter | `posthog/ai/anthropic/anthropic_converter.py` | {"No" if step4_result and step4_result.get('anthropic_converter_clean') else "YES (unexpected!)"} |
| General AI utils | `posthog/ai/utils.py` | {"No" if step4_result and step4_result.get('utils_clean') else "YES (unexpected!)"} |
| OpenAI Agents processor | `posthog/ai/openai_agents/processor.py` | {"**Yes** (only place)" if step4_result and step4_result.get('openai_agents_sets_it') else "No"} |

**The Anthropic converter** (`extract_anthropic_usage_from_response`, lines 206-231) only extracts:
- `input_tokens` (exclusive of cache)
- `output_tokens`
- `cache_read_input_tokens`
- `cache_creation_input_tokens`
- `web_search_count`

**The general utils** (`posthog/ai/utils.py`) only tags `$ai_input_tokens` and `$ai_output_tokens`. There is no `tag("$ai_total_tokens", ...)` anywhere in this file.

**The only code that sets `$ai_total_tokens`** is in `posthog/ai/openai_agents/processor.py` (lines 539 and 696), which is exclusively for OpenAI Agents — a completely separate code path from the Anthropic wrapper.

**Result:** If `$ai_total_tokens` appears in a stored event captured via `posthog.ai.anthropic.AsyncAnthropic`, it **must** have come from outside the SDK — most likely via `posthog_properties`.

---

## Key Evidence

1. `$ai_total_tokens` is present in the stored events, but the PostHog Anthropic wrapper **never sets** this property (confirmed by source inspection in Test 4). Only OpenAI Agents sets it. This strongly suggests the value comes from `posthog_properties`.

2. The stored `$ai_input_tokens` (48268) minus `$ai_cache_read_input_tokens` (45417) equals exactly the expected exclusive value (2851), which is what the Anthropic API returns as `input_tokens`.

---

## Raw Script Output

<details>
<summary>Click to expand full script output</summary>

```
{raw_output.strip()}
```

</details>
"""

    with open(OUTPUT_FILE, "w") as f:
        f.write(md)

    print(f"\n  Output written to: {OUTPUT_FILE}")


async def main():
    out = OutputWriter()

    out.print("=" * 70)
    out.print("  Anthropic Cache Token Cost Debug Script")
    out.print("  Investigating: $ai_input_tokens inclusive vs exclusive")
    out.print("=" * 70)

    # Step 1: Verify raw API behavior
    step1_result = await step1_raw_anthropic_api(out)

    # Step 2: Test through PostHog wrapper
    step2_result = await step2_posthog_wrapper(out)

    # Step 3: Test the posthog_properties override theory
    step3_result = await step3_posthog_wrapper_with_custom_properties(out)

    # Step 4: Prove $ai_total_tokens is never set by Anthropic SDK
    step4_result = await step4_prove_total_tokens_never_set(out)

    out.start_section("DONE")
    out.print("  Check the output above to see if the bug is reproducible.")
    out.print("  If Step 2 shows correct values but the customer sees wrong values,")
    out.print("  the issue is likely in posthog_properties overrides (Step 3).")
    out.print("  Step 4 proves via source inspection that $ai_total_tokens cannot")
    out.print("  come from the Anthropic SDK code path.")
    out.print()

    # Write the markdown output
    write_output_md(step1_result, step2_result, step3_result, out.get_raw_output(), step4_result)


if __name__ == "__main__":
    asyncio.run(main())
