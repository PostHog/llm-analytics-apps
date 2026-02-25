# Anthropic Cache Token Cost - Debug Results

**Date:** 2026-02-25 11:17 UTC
**Model:** `claude-haiku-4-5-20251001`
**PostHog Python SDK:** `v7.9.3`
**Anthropic SDK:** `v0.75.0`

---

## TL;DR

The PostHog Python SDK (`posthog.ai.anthropic.AsyncAnthropic`) correctly passes through the **exclusive** `input_tokens` value from the Anthropic API. The SDK does **not** modify or inflate this value.

However, if you pass `posthog_properties` to `messages.create()` containing `$ai_input_tokens` or `$ai_total_tokens`, those values **override** the SDK's correct values. This can cause inflated cost calculations if the overriding values include cached tokens in the input count.

---

## Test 1: Raw Anthropic API Behavior

Verified that the Anthropic API returns `input_tokens` **exclusive** of cached tokens:

| Field | Value |
|-------|-------|
| `input_tokens` | 13 |
| `cache_read_input_tokens` | 14100 |
| `cache_creation_input_tokens` | 14100 |
| `output_tokens` | 41 |

**Result:** `input_tokens` (13) is much smaller than `cache_read_input_tokens` (14100), confirming Anthropic returns **exclusive** counts.

---

## Test 2: PostHog SDK Wrapper (No Custom Properties)

Spied on `ph_client.capture()` to see what the SDK sends to PostHog:

| Field | Anthropic API | PostHog SDK |
|-------|--------------|-------------|
| `input_tokens` / `$ai_input_tokens` | 13 | 13 |
| `cache_read_input_tokens` / `$ai_cache_read_input_tokens` | 14100 | 14100 |
| `$ai_total_tokens` | N/A | NOT SET |

**Result:** SDK correctly passes through the exclusive value.

The Anthropic wrapper does NOT set `$ai_total_tokens` - this is expected.

---

## Test 3: `posthog_properties` Override (Root Cause)

### 3a) Direct Override Test

Passed `posthog_properties={"$ai_input_tokens": 99999}` to `messages.create()`.

**Result:** The SDK's correct value was **overridden** to 99999. This confirms `posthog_properties` takes precedence.

### 3b) Simulated Customer Pattern

Simulated what happens when a customer computes inclusive token counts and passes them via `posthog_properties`:

```python
# Customer code pattern that causes the overcharge:
inclusive_input = response.usage.input_tokens + response.usage.cache_read_input_tokens
total = inclusive_input + response.usage.output_tokens

client.messages.create(
    ...,
    posthog_properties={
        "$ai_input_tokens": inclusive_input,   # WRONG - includes cached tokens!
        "$ai_total_tokens": total,
    },
)
```

| Field | Correct (Exclusive) | Wrong (Inclusive) |
|-------|-------------------|-----------------|
| `$ai_input_tokens` | 12 | 14113 |
| `$ai_cache_read_input_tokens` | 14100 | 14100 |
| `$ai_total_tokens` | not set | 14149 |

### Cost Impact

Using `claude-haiku-4-5` pricing ($1/Mtok input, $0.10/Mtok cache read):

| | Correct | Overcharged |
|--|---------|-------------|
| Uncached input cost | $0.001422 | $0.015523 |
| **Overcharge factor** | | **10.9x** |

---

## How to Check if This Affects You

Look for any code that passes `posthog_properties` to `messages.create()` with token-related fields:

```python
# Search your codebase for patterns like:
client.messages.create(
    ...,
    posthog_properties={
        "$ai_input_tokens": ...,    # This overrides the SDK!
        "$ai_total_tokens": ...,    # This also overrides!
    },
)
```

The SDK already extracts the correct exclusive `input_tokens` from the Anthropic response. You do **not** need to pass these values yourself.

### What to Do

**Option A (Recommended):** Remove `$ai_input_tokens` and `$ai_total_tokens` from your `posthog_properties`. The SDK handles these correctly.

**Option B:** If you need to pass custom properties, make sure `$ai_input_tokens` uses the **exclusive** value from `response.usage.input_tokens` (not `input_tokens + cache_read_input_tokens`).

---

## Key Evidence

1. `$ai_total_tokens` is present in the stored events, but the PostHog Anthropic wrapper **never sets** this property. Only OpenAI Agents sets it. This strongly suggests the value comes from `posthog_properties`.

2. The stored `$ai_input_tokens` (48268) minus `$ai_cache_read_input_tokens` (45417) equals exactly the expected exclusive value (2851), which is what the Anthropic API returns as `input_tokens`.

---

## Raw Script Output

<details>
<summary>Click to expand full script output</summary>

```
======================================================================
  Anthropic Cache Token Cost Debug Script
  Investigating: $ai_input_tokens inclusive vs exclusive
======================================================================

======================================================================
  STEP 1: Raw Anthropic API (no PostHog wrapper)
======================================================================
  Making two calls to populate cache, then checking usage on second call...

  Call 1 (cache miss - should create cache)...

  Call 1 usage:
    input_tokens:                13
    output_tokens:               39
    cache_read_input_tokens:     0
    cache_creation_input_tokens: 14100

  Call 2 (cache hit expected)...

  Call 2 usage:
    input_tokens:                13
    output_tokens:               41
    cache_read_input_tokens:     14100
    cache_creation_input_tokens: 0

  Analysis:
    input_tokens (from API):       13
    cache_read_input_tokens:       14100
    input + cache_read:            14113
    => input_tokens is EXCLUSIVE of cache (correct Anthropic behavior)

======================================================================
  STEP 2: PostHog AsyncAnthropic wrapper (spy on capture)
======================================================================

  Call 1 (cache miss - populating cache)...

  [SPY] ph_client.capture() called!
    event:                         $ai_generation
    $ai_provider:                  anthropic
    $ai_model:                     claude-haiku-4-5-20251001
    $ai_input_tokens:              13
    $ai_output_tokens:             41
    $ai_cache_read_input_tokens:   14100
    $ai_cache_creation_input_tokens: None
    $ai_total_tokens:              NOT SET

  Raw API usage (call 1):
    input_tokens:                13
    output_tokens:               41
    cache_read_input_tokens:     14100
    cache_creation_input_tokens: 0

  Call 2 (cache hit expected)...

  [SPY] ph_client.capture() called!
    event:                         $ai_generation
    $ai_provider:                  anthropic
    $ai_model:                     claude-haiku-4-5-20251001
    $ai_input_tokens:              13
    $ai_output_tokens:             41
    $ai_cache_read_input_tokens:   14100
    $ai_cache_creation_input_tokens: None
    $ai_total_tokens:              NOT SET

  Raw API usage (call 2):
    input_tokens:                13
    output_tokens:               41
    cache_read_input_tokens:     14100
    cache_creation_input_tokens: 0

======================================================================
  COMPARISON (Call 2 - cache hit)
======================================================================
    Anthropic API input_tokens:   13
    SDK $ai_input_tokens:         13
    cache_read_input_tokens:      14100
    API input + cache_read:       14113

    RESULT: SDK correctly passes through EXCLUSIVE input_tokens

    OK: $ai_total_tokens is not set (expected for Anthropic wrapper)

======================================================================
  STEP 3: Test posthog_properties override (leading theory)
======================================================================
  Simulating customer passing their own inclusive token counts via posthog_properties...

  3a) Simple override with hardcoded values...
    Anthropic API input_tokens:   13
    SDK $ai_input_tokens:         99999
    $ai_total_tokens:             100599
    => posthog_properties OVERRIDES the SDK's correct value

  3b) Simulating customer computing inclusive tokens from the response...
  (Customer code might do: input_tokens = usage.input_tokens + usage.cache_read_input_tokens)
    Customer computes: inclusive_input = 13 + 14100 = 14113
    Customer computes: total = 14113 + 36 = 14149
    Anthropic API input_tokens:         12 (exclusive)
    Anthropic API cache_read:           14100
    Anthropic API output_tokens:        100
    ---
    Stored $ai_input_tokens:            14113 (inclusive!)
    Stored $ai_cache_read_input_tokens: 14100
    Stored $ai_total_tokens:            14149
    ---
    COST COMPARISON (haiku pricing: $1/Mtok input, $0.10/Mtok cache):

    Correct (exclusive input_tokens = 12):
      uncached: 12 * $1/Mtok    = $0.000012
      cached:   14100 * $0.10/Mtok = $0.001410
      total input cost:                    $0.001422

    Wrong (inclusive input_tokens = 14113, treated as exclusive):
      uncached: 14113 * $1/Mtok    = $0.014113
      cached:   14100 * $0.10/Mtok = $0.001410
      total input cost:                    $0.015523

    OVERCHARGE: 10.9x (992% more)

======================================================================
  DONE
======================================================================
  Check the output above to see if the bug is reproducible.
  If Step 2 shows correct values but the customer sees wrong values,
  the issue is likely in posthog_properties overrides (Step 3).
```

</details>
