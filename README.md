# LLM Analytics Apps

Internal tooling for the PostHog LLM Analytics team. Contains demo data generators, trace generators, test scripts, and a runner for the SDK examples that live in [posthog-python](https://github.com/PostHog/posthog-python) and [posthog-js](https://github.com/PostHog/posthog-js).

For copy-paste-able provider integration examples, see the `examples/example-ai-*` directories in each SDK repo.

## Setup

Requires:
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)
- [phrocs](https://github.com/PostHog/posthog/tre/master/tools/phrocs)

```bash
cp .env.example .env
# Fill in your API keys in .env
make setup
```

## Tools

### SDK Example Runner

Discovers and runs all `example-ai-*` examples from sibling `posthog-python` and `posthog-js` repos.

```bash
# List all available examples (with cache status)
./run-examples.sh --list

# Run a specific example or group by name
./run-examples.sh anthropic        # all anthropic examples
./run-examples.sh python/openai    # python openai examples only

# Run all examples in parallel via phrocs
./run-examples.sh --parallel

# Run all sequentially
./run-examples.sh --all

# Force re-run (ignore cache)
./run-examples.sh --rerun --all

# Install dependencies for all examples
./run-examples.sh --install
```

### Demo Data Generator

Generates realistic multi-turn conversations across all supported providers using the PostHog AI SDKs directly. Useful for populating a PostHog instance with representative LLM analytics data.

```bash
make demo-data                # 5 conversations, random providers
make demo-data-quick          # 3 short conversations, single provider
make demo-data-tools          # tool-heavy conversations
make demo-data-negative       # negative sentiment for testing
```

### Trace Generator

Creates complex nested LLM trace data (traces, spans, generations) without making real LLM calls. Useful for testing PostHog's trace visualization.

```bash
make run-trace-generator
```

### Test Scripts

Various scripts for testing specific SDK integrations:

```bash
# Python
uv run scripts/test_litellm.py
uv run scripts/test_langchain_otel.py
uv run scripts/test_pydantic_ai_otel.py

# Node (Vercel AI SDK)
npx tsx scripts/test_vercel_ai_otel.ts
npx tsx scripts/test_vercel_anthropic.ts
```

## Local SDK Development

To develop against local SDK checkouts, set these in `.env`:

```bash
POSTHOG_PYTHON_PATH=../../posthog-python
POSTHOG_JS_PATH=../../posthog-js
```

## License

MIT License - see LICENSE file for details.
