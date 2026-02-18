# LLM Analytics Apps

Example implementations of various LLM providers using PostHog's AI SDKs. This repository demonstrates how to integrate multiple AI providers (Anthropic, OpenAI, Google Gemini) with PostHog for analytics tracking.

## 🔧 Prerequisites

### For Python:
- Python 3.8 or higher
- pip package manager

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

2. **Run the application:**

   Unified shell (recommended):
   ```bash
   pnpm install
   pnpm start
   ```

   Or from repo root:
   ```bash
   make run-cli
   ```

   For Python:
   ```bash
   cd python
   ./run.sh
   ```

   For Node.js:
   ```bash
   cd node
   ./run.sh
   ```

### Unified Shell Defaults

- Runtime: `Node`
- Provider: `OpenAI Chat Completions`
- Streaming: `On`

Provider options (for example `S` streaming, `T` thinking) are available from selectors and chat.

The `run.sh` script will automatically:
- Set up a virtual environment (Python) or install dependencies (Node)
- Install all required packages
- Start the interactive CLI

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

### 🎯 LLM Trace Generator
An interactive tool for creating complex nested LLM trace data for testing PostHog analytics. Features pre-built templates (simple chat, RAG pipeline, multi-agent) and a custom trace builder for creating arbitrarily complex structures.

```bash
cd python/trace-generator
./run.sh
```

## 🛠️ Development

### Local Development with PostHog SDKs

If you're developing the PostHog SDKs locally, you can use local paths instead of published packages:

1. Set environment variables in your `.env`:
   ```bash
   # For local PostHog SDK development
   POSTHOG_PYTHON_PATH=/../posthog-python
   POSTHOG_JS_PATH=/../posthog-js
   ```

2. Run the application normally with `./run.sh`

The scripts will automatically detect and use your local SDK versions.

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🔗 Links

- [PostHog Documentation](https://posthog.com/docs)
- [PostHog Python SDK](https://github.com/PostHog/posthog-python)
- [PostHog JavaScript SDK](https://github.com/PostHog/posthog-js)
