.PHONY: setup run-trace-generator run-trace-generator-debug demo-data demo-data-quick demo-data-tools demo-data-negative

## Install all dependencies
setup:
	@uv sync
	@pnpm install

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
