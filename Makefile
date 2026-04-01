.PHONY: setup examples examples-list examples-all examples-parallel examples-install run-trace-generator run-trace-generator-debug demo-data demo-data-quick demo-data-tools demo-data-negative install-local-sdk test-claude-agent-sdk test-claude-agent-sdk-interactive

## Install all dependencies
setup:
	@uv sync
	@pnpm install

## Run the interactive example picker (sources .env, discovers examples from sibling SDK repos)
examples:
	@./run-examples.sh

## List all available examples
examples-list:
	@./run-examples.sh --list

## Run all examples sequentially
examples-all:
	@./run-examples.sh --all

## Run all examples in parallel via mprocs (or filtered: make examples-parallel F=anthropic)
examples-parallel:
	@./run-examples.sh --parallel $(F)

## Install dependencies for all examples
examples-install:
	@./run-examples.sh --install

## Run the trace generator (mock trace data, no LLM calls)
run-trace-generator:
	@uv run trace-generator/trace_generator.py

run-trace-generator-debug:
	@DEBUG=1 uv run trace-generator/trace_generator.py

## Generate demo data (5 conversations, random providers, 5 turns each)
demo-data:
	@uv run scripts/generate_demo_data.py --conversations 5 --max-turns 5 --parallel 3

## Quick demo data (3 short conversations)
demo-data-quick:
	@uv run scripts/generate_demo_data.py --conversations 3 --max-turns 3 --parallel 3 --providers openai_chat

## Generate tool-heavy demo conversations (weather lookups, jokes across multiple cities)
demo-data-tools:
	@uv run scripts/generate_demo_data.py --tools --conversations 5 --max-turns 6 --parallel 3

## Generate negative/angry demo conversations for sentiment testing
demo-data-negative:
	@uv run scripts/generate_demo_data.py --conversations 3 --max-turns 4 --parallel 3 --providers openai_chat --persona "an extremely frustrated customer who has been passed around to 5 different support agents" --topic "complaining about a product that keeps breaking"

## Install local posthog-python for development (required for claude-agent-sdk integration)
install-local-sdk:
	@uv sync
	@uv pip install -e ../posthog-python
	@echo "Local posthog-python installed. Use 'make test-claude-agent-sdk' to run."

## Claude Agent SDK test (requires local posthog-python with integration)
test-claude-agent-sdk:
	@uv run --no-sync scripts/test_claude_agent_sdk.py

## Claude Agent SDK interactive mode
test-claude-agent-sdk-interactive:
	@uv run --no-sync scripts/test_claude_agent_sdk.py --interactive
