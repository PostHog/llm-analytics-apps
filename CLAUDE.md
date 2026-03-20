# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Internal tooling for the PostHog LLM Analytics team. Provider examples have been moved to the SDK repos (`posthog-python` and `posthog-js`) as `examples/example-ai-*` directories.

What remains here:
- **Demo data generator** (`python/scripts/generate_demo_data.py`) — generates realistic multi-turn conversations using PostHog AI SDKs
- **Trace generator** (`python/trace-generator/`) — creates mock LLM trace data without real API calls
- **Test scripts** (`python/scripts/`, `node/scripts/`) — integration tests for specific SDK features
- **Example runner** (`run-examples.sh`) — discovers and runs examples from sibling SDK repos

## Key Commands

```bash
# Run SDK examples from sibling repos
make examples-list              # list all available examples
make examples-parallel          # run all in parallel via mprocs
./run-examples.sh anthropic     # run by name filter

# Generate demo data
make demo-data                  # 5 conversations, random providers
make demo-data-quick            # 3 short, single provider

# Trace generator (no LLM calls)
make run-trace-generator

# Setup
cd python && ./run.sh           # python venv + deps
cd node && ./run.sh             # node deps via pnpm
```

## Architecture

### Python (`python/`)
- `run.sh` — sets up venv, installs deps from `requirements.txt`
- `scripts/generate_demo_data.py` — multi-provider demo data using `posthog.ai` SDK wrappers
- `scripts/test_*.py` — individual integration tests
- `trace-generator/` — mock trace builder
- `screenshot-demo/` — UI screenshot tool

### Node.js (`node/`)
- `run.sh` — installs deps via pnpm, handles local SDK symlinks
- `scripts/test_*.ts` — integration tests (Vercel AI, OTel)

### Configuration

Environment variables in `.env`:
- `POSTHOG_API_KEY`, `POSTHOG_HOST` — PostHog connection
- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY` — provider keys
- `POSTHOG_PYTHON_PATH`, `POSTHOG_JS_PATH` — local SDK paths for development
- `POSTHOG_PYTHON_VERSION`, `POSTHOG_JS_AI_VERSION` — specific published versions

### Trace Generator Event Types

The trace generator creates three event types:
- `$ai_trace` — top-level trace events
- `$ai_span` — intermediate span events (nestable)
- `$ai_generation` — LLM generation events with model and token info
