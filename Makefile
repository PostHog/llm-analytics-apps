.PHONY: examples examples-list examples-all examples-python examples-node run-trace-generator run-trace-generator-debug demo-data demo-data-quick demo-data-tools demo-data-negative

## Run the interactive example picker (sources .env, discovers examples from sibling SDK repos)
examples:
	@./run-examples.sh

## List all available examples
examples-list:
	@./run-examples.sh --list

## Run all examples sequentially
examples-all:
	@./run-examples.sh --all

## Run only Python examples
examples-python:
	@./run-examples.sh --filter "[python]"

## Run only Node.js examples
examples-node:
	@./run-examples.sh --filter "[node]"

## Run examples matching a pattern (e.g., make examples-filter F=anthropic)
examples-filter:
	@./run-examples.sh --filter "$(F)"

## Run the trace generator (mock trace data, no LLM calls)
run-trace-generator:
	@cd python/trace-generator && ./run.sh

run-trace-generator-debug:
	@cd python/trace-generator && DEBUG=1 ./run.sh

## Generate demo data (5 conversations, random providers, 5 turns each)
demo-data:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --conversations 5 --max-turns 5 --parallel 3

## Quick demo data (3 short conversations)
demo-data-quick:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --conversations 3 --max-turns 3 --parallel 3 --providers openai_chat

## Generate tool-heavy demo conversations (weather lookups, jokes across multiple cities)
demo-data-tools:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --tools --conversations 5 --max-turns 6 --parallel 3

## Generate negative/angry demo conversations for sentiment testing
demo-data-negative:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --conversations 3 --max-turns 4 --parallel 3 --providers openai_chat --persona "an extremely frustrated customer who has been passed around to 5 different support agents" --topic "complaining about a product that keeps breaking"
