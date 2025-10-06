# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a demonstration repository showcasing PostHog AI SDK integrations with multiple LLM providers. It contains parallel implementations in both Python and Node.js, each providing interactive CLIs for testing various AI provider integrations with PostHog analytics tracking.

## Key Commands

### Running the Applications

```bash
# Python implementation
cd python && ./run.sh

# Node.js implementation
cd node && ./run.sh

# Or use the Makefile
make run-python
make run-node
```

The `run.sh` scripts automatically:
- Set up virtual environments (Python) or install dependencies (Node.js)
- Handle local SDK development paths (via `.env` configuration)
- Install required packages
- Start the interactive CLI

### Debug Mode

Enable detailed API call logging in two ways:

**Option 1: Set DEBUG in `.env` file:**
```bash
DEBUG=1
```

**Option 2: Use the debug make targets:**
```bash
make run-python-debug
make run-node-debug
```

When enabled, debug mode will log:
- Complete API request payloads (model, parameters, messages, tools)
- Complete API response payloads (response content, tokens, metadata)
- Formatted as bordered blocks with 🐛 prefix for easy identification
- Automatically truncates very long outputs (>2000 chars)

Debug logging is implemented in the base provider classes with two helper methods:

**Simple API logging** (recommended):
```python
# Python
self._debug_api_call("ProviderName", request_params, response)

# Node.js
this.debugApiCall("ProviderName", requestParams, response);
```

This helper automatically converts objects to JSON and logs both request and response. Just pass your raw request parameters and response objects - no need to manually construct dictionaries.

**Custom logging** (for special cases):
```python
# Python
self._debug_log("Custom Title", data)

# Node.js
this.debugLog("Custom Title", data);
```

See `python/providers/anthropic.py` and `node/src/providers/anthropic.ts` for usage examples.

### Building and Development (Node.js)

```bash
cd node
npm run build    # Compile TypeScript to dist/
npm run dev      # Run directly with ts-node
npm run clean    # Remove dist/ directory
```

### Trace Generator Tool

```bash
cd python/trace-generator && ./run.sh

# Or use the make target
make run-trace-generator
make run-trace-generator-debug
```

Creates complex nested LLM trace data for testing PostHog analytics. Features pre-built templates (simple chat, RAG pipeline, multi-agent) and a custom trace builder.

## Architecture

### Dual Implementation Structure

The repository maintains **parallel implementations** in Python (`python/`) and Node.js (`node/`), with matching provider abstractions and functionality. Both implementations share:
- A common `.env` configuration at the root
- The same CLI menu structure and test modes
- Equivalent provider implementations (Anthropic, OpenAI, Gemini, LangChain, etc.)

### Provider Architecture

Both implementations use an **abstract base provider pattern**:

**Python**: `providers/base.py` defines `BaseProvider` and `StreamingProvider` abstract classes
**Node.js**: `src/providers/base.ts` defines `BaseProvider` and `StreamingProvider` abstract classes

All provider implementations inherit from these base classes and implement:
- `get_name()` / `getName()`: Provider identification
- `chat()`: Non-streaming message handling
- `chat_stream()` / `chatStream()`: Streaming message handling (for streaming providers)
- `get_tool_definitions()` / `getToolDefinitions()`: Tool/function calling definitions

### Provider Implementations

#### Python Providers (`python/providers/`)
- `anthropic.py` / `anthropic_streaming.py`
- `gemini.py` / `gemini_streaming.py`
- `openai.py` / `openai_chat.py` / `openai_streaming.py` / `openai_chat_streaming.py`
- `langchain.py`
- `litellm_provider.py`

#### Node.js Providers (`node/src/providers/`)
- `anthropic.ts` / `anthropic-streaming.ts`
- `gemini.ts` / `gemini-streaming.ts`
- `openai.ts` / `openai-chat.ts` / `openai-streaming.ts` / `openai-chat-streaming.ts`
- `langchain.ts`
- `vercel-ai.ts` / `vercel-ai-streaming.ts`
- `vercel-generate-object.ts` / `vercel-stream-object.ts`

### PostHog Integration

All providers receive a shared PostHog client instance (`posthog_client` / `posthogClient`) initialized in the main entry files:
- Python: `python/main.py` creates a global `posthog` client
- Node.js: `node/src/index.ts` creates a global `posthog` client

Providers use the PostHog AI SDK wrappers (e.g., `@posthog/ai` for Node.js, `posthog` Python SDK with AI features) to automatically track LLM events including traces, spans, and generations.

### Test Modes

Both implementations support identical test modes via CLI menu:
1. **Chat Mode**: Interactive conversation
2. **Tool Call Test**: Automated weather tool calling test
3. **Message Test**: Simple greeting test
4. **Image Test**: Image description capabilities test
5. **Embeddings Test**: Embedding generation (OpenAI only)
6. **Structured Output Test**: Structured data generation (Node.js Vercel AI only)

### Local Development with PostHog SDKs

The `run.sh` scripts detect environment variables to use local SDK paths instead of published packages:

```bash
# .env configuration
POSTHOG_PYTHON_PATH=/../posthog-python
POSTHOG_JS_PATH=/../posthog-js
LITELLM_PATH=/../litellm

# Or use specific versions
POSTHOG_PYTHON_VERSION=6.6.1
POSTHOG_JS_AI_VERSION=6.1.2
POSTHOG_JS_NODE_VERSION=5.7.0
```

The scripts automatically handle editable installs (`pip install -e` or `npm install`) for local development.

## Important Patterns

### Adding a New Provider

1. Create provider file in `providers/` directory (Python or Node.js)
2. Extend `BaseProvider` or `StreamingProvider`
3. Implement required abstract methods
4. Initialize PostHog AI SDK wrapper for the specific provider
5. Add provider to the imports and provider map in `main.py` / `index.ts`
6. Add menu option in `display_providers()` / `displayProviders()`

### PostHog Event Structure

The PostHog AI SDK automatically creates events with properties:
- `$ai_trace_id`: Unique identifier for the entire conversation/request
- `$ai_span_id`: Unique identifier for individual operations
- `$ai_parent_id`: Links child spans to parent spans
- `$ai_model`: Model name used
- `$ai_provider`: Provider name
- `$ai_input` / `$ai_input_state`: Input data
- `$ai_output` / `$ai_output_state` / `$ai_output_choices`: Output data
- `$ai_latency`: Operation duration
- `$ai_input_tokens` / `$ai_output_tokens`: Token usage

### Trace Generator Event Types

The trace generator (`python/trace-generator/trace_generator.py`) creates three event types:
- `$ai_trace`: Top-level trace events
- `$ai_span`: Intermediate span events (can be nested)
- `$ai_generation`: LLM generation events with model and token information
