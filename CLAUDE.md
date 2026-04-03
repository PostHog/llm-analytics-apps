# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Internal tooling for the PostHog LLM Analytics team. Provider examples have been moved to the SDK repos (`posthog-python` and `posthog-js`) as `examples/example-ai-*` directories.

What remains here:
- **Demo data generator** (`scripts/generate_demo_data.py`) — generates realistic multi-turn conversations using PostHog AI SDKs
- **Trace generator** (`trace-generator/`) — creates mock LLM trace data without real API calls
- **Test scripts** (`scripts/test_*.py`) — integration tests for specific SDK features
- **Example runner** (`run-examples.sh`) — discovers and runs examples from sibling SDK repos
- **Screenshot demo** (`screenshot-demo/`) — UI screenshot tool

## Key Commands

```bash
# Setup
make setup                      # install deps via uv

# Run SDK examples from sibling repos
./run-examples.sh --list            # list all available examples
./run-examples.sh --parallel        # run all in parallel via phrocs
./run-examples.sh anthropic         # run by name filter

# Generate demo data
make demo-data                  # 5 conversations, random providers
make demo-data-quick            # 3 short, single provider

# Trace generator (no LLM calls)
make run-trace-generator

# Run individual scripts
uv run scripts/test_litellm.py
```

## Project Structure

```
├── pyproject.toml              # Python dependencies (managed by uv)
├── package.json                # Node dependencies (managed by pnpm)
├── Makefile                    # all common tasks
├── run-examples.sh             # SDK example runner
├── scripts/                    # demo data and test scripts
│   ├── generate_demo_data.py   # multi-provider demo data
│   ├── test_*.py               # Python integration tests
│   └── test_*.ts               # Node integration tests (Vercel AI, OTel)
├── trace-generator/            # mock trace builder
└── screenshot-demo/            # UI screenshot tool
```

## Configuration

Environment variables in `.env`:
- `POSTHOG_API_KEY`, `POSTHOG_HOST` — PostHog connection
- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY` — provider keys
- `POSTHOG_PYTHON_PATH`, `POSTHOG_JS_PATH` — local SDK paths for development

## Trace Generator Event Types

The trace generator creates three event types:
- `$ai_trace` — top-level trace events
- `$ai_span` — intermediate span events (nestable)
- `$ai_generation` — LLM generation events with model and token info
