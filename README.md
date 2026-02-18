# LLM Analytics Apps

Example implementations of various LLM providers using PostHog's AI SDKs. This repository demonstrates how to integrate multiple AI providers (Anthropic, OpenAI, Google Gemini) with PostHog for analytics tracking.

## 🔧 Prerequisites

### For Python:
- Python 3.8 or higher
- uv package manager

### For Node.js:
- Node.js 24 or higher
- npm or pnpm package manager

## ⚙️ Setup

1. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your API keys:
   - `ANTHROPIC_API_KEY`: Your Anthropic API key
   - `GEMINI_API_KEY`: Your Google Gemini API key
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `POSTHOG_API_KEY`: Your PostHog API key
   - `POSTHOG_HOST`: PostHog host (defaults to https://app.posthog.com)
   - Optional Node package overrides:
     - `POSTHOG_JS_PATH` (local posthog-js monorepo path)
     - `POSTHOG_JS_AI_VERSION` / `POSTHOG_JS_NODE_VERSION` (pinned npm versions)
   - Optional Python package overrides:
     - `POSTHOG_PYTHON_PATH` (local posthog-python path)
     - `POSTHOG_PYTHON_VERSION` (pinned PyPI version)
     - `LITELLM_PATH` (local litellm path)

2. **Run the application:**

   Unified shell (recommended):
   ```bash
   pnpm install
   pnpm start
   ```

   Dev mode (auto rebuild + auto restart on TS changes):
   ```bash
   pnpm dev
   ```
   
   When `POSTHOG_HOST=http://localhost:8010`, the CLI automatically syncs
   `POSTHOG_API_KEY` from your local PostHog instance at startup.

### Runtime Tools (via CLI)

Runtime-specific tools are exposed directly in the unified shell:

- Press `T` from the menu to open Runtime Tools.
- Select a tool and run it in-place.
- Output is shown in the TUI (`R` to rerun, scroll supported).

Runtime setup logs are written to:
- `.logs/runtime-node-setup.log`
- `.logs/runtime-python-setup.log`

### Unified Shell Defaults

- Runtime: `Node`
- Provider: `OpenAI Chat Completions`
- Streaming: `On`

Provider options (for example `S` streaming, `T` thinking) are available from selectors and chat.

## 🎮 Usage

### Test Modes
- **Chat Mode**: Interactive conversation with the selected provider
- **Tool Call Test**: Automatically tests weather tool calling
- **Message Test**: Simple greeting test
- **Image Test**: Tests image description capabilities
- **Embeddings Test**: Tests embedding generation (OpenAI only)

### 🧠 Extended Thinking (Anthropic Claude)

Claude's extended thinking feature allows the model to show its internal reasoning process before responding. This can improve response quality for complex problems.

**How to use:**

When you select an Anthropic provider (options 1 or 2), you'll be prompted:

```
🧠 Extended Thinking Configuration
==================================================
Extended thinking shows Claude's reasoning process.
This can improve response quality for complex problems.
==================================================

Enable extended thinking? (y/n) [default: n]: y
Thinking budget tokens (1024-32000) [default: 10000]: 15000

✅ Initialized Anthropic (Thinking: enabled, budget: 15000)
```

**How it works:**
- The CLI will ask if you want to enable thinking each time you select an Anthropic provider
- You can customize the thinking budget (min: 1024, recommended: 10000-15000)
- Claude will show its reasoning process prefixed with "💭 Thinking:"
- Larger budgets can improve response quality for complex problems
- The model may not use the entire allocated budget
- Works with both regular and streaming Anthropic providers
- `max_tokens` is automatically adjusted to accommodate both thinking and response

**Example output:**
```
👤 You: Are there an infinite number of prime numbers such that n mod 4 == 3?

💭 Thinking: Let me think about this systematically. I need to consider 
the distribution of primes and their properties modulo 4...

🤖 Bot: Yes, there are infinitely many prime numbers of the form 4k + 3...
```

## 🛠️ Development

### Local Development with PostHog SDKs

If you're developing the PostHog SDKs locally, you can use local paths instead of published packages:

1. Set environment variables in your `.env`:
   ```bash
   # For local PostHog SDK development
   POSTHOG_PYTHON_PATH=/../posthog-python
   ```

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🔗 Links

- [PostHog Documentation](https://posthog.com/docs)
- [PostHog Python SDK](https://github.com/PostHog/posthog-python)
- [PostHog JavaScript SDK](https://github.com/PostHog/posthog-js)
