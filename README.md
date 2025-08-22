# LLM Analytics Apps

Example implementations of various LLM providers using PostHog's AI SDKs. This repository demonstrates how to integrate multiple AI providers (Anthropic, OpenAI, Google Gemini) with PostHog for analytics tracking.

## 🔧 Prerequisites

### For Python:
- Python 3.8 or higher
- pip package manager

### For Node.js:
- Node.js 16 or higher
- npm package manager

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
