# Debug: Anthropic Cache Token Cost

Reproduction script for investigating Anthropic cache token cost discrepancies in the PostHog Python SDK.

## The Issue

When using `posthog.ai.anthropic.AsyncAnthropic` with Anthropic's prompt caching, the stored `$ai_input_tokens` can end up as the **inclusive** value (input + cache_read tokens) instead of the **exclusive** value that the Anthropic API returns. This causes the cost calculator to overcharge by treating all tokens (including cached ones) at the full prompt rate.

## What This Script Tests

1. **Raw Anthropic API** - Confirms the API returns `input_tokens` exclusive of cached tokens
2. **PostHog SDK wrapper** - Confirms the SDK correctly passes through the exclusive value
3. **`posthog_properties` override** - Demonstrates how passing custom properties can override the SDK's correct values

## Usage

```bash
cd python
python scripts/debug-anthropic-cache-cost/run.py
```

Requires `ANTHROPIC_API_KEY` and `POSTHOG_API_KEY` in the root `.env` file.

Results are written to `output.md` (gitignored) in this directory.
