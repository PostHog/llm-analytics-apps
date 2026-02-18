.PHONY: run-cli run-cli-debug build-cli run-python run-node run-python-debug run-node-debug run-trace-generator run-trace-generator-debug run-screenshot-demo run-screenshot-demo-debug python-install python-install-reset python-install-local test-python-weather ingest-trace demo-data demo-data-quick demo-data-negative

run-cli:
	@pnpm start

run-cli-debug:
	@DEBUG=1 pnpm start

build-cli:
	@pnpm build

run-python:
	@cd python && ./run.sh

run-node:
	@cd node && ./run.sh

run-python-debug:
	@cd python && DEBUG=1 ./run.sh

run-node-debug:
	@cd node && DEBUG=1 ./run.sh

run-trace-generator:
	@cd python/trace-generator && ./run.sh

run-trace-generator-debug:
	@cd python/trace-generator && DEBUG=1 ./run.sh

run-screenshot-demo:
	@cd python/screenshot-demo && ./run.sh

run-screenshot-demo-debug:
	@cd python/screenshot-demo && DEBUG=1 ./run.sh

## Install Python deps only (don’t run app). Respects POSTHOG_PYTHON_PATH or POSTHOG_PYTHON_VERSION
python-install:
	@cd python && INSTALL_ONLY=1 ./run.sh

## Install Python deps after removing existing posthog from venv (helpful when switching sources)
python-install-reset:
	@cd python && RESET_POSTHOG=1 INSTALL_ONLY=1 ./run.sh

## Convenience: install using local posthog-python checkout
# Usage: make python-install-local POSTHOG_PYTHON_PATH=/absolute/path/to/posthog-python
python-install-local:
	@cd python && INSTALL_ONLY=1 POSTHOG_PYTHON_PATH="$(POSTHOG_PYTHON_PATH)" ./run.sh

## Test Python weather tool functionality
test-python-weather:
	@cd python && ./scripts/run_test.sh

## Generate demo data (5 conversations, random providers, 5 turns each)
demo-data:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --conversations 5 --max-turns 5 --parallel 3

## Quick demo data (3 short conversations)
demo-data-quick:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --conversations 3 --max-turns 3 --parallel 3 --providers openai_chat

## Generate negative/angry demo conversations for sentiment testing
demo-data-negative:
	@cd python && source venv/bin/activate && python scripts/generate_demo_data.py --conversations 3 --max-turns 4 --parallel 3 --providers openai_chat --persona "an extremely frustrated customer who has been passed around to 5 different support agents" --topic "complaining about a product that keeps breaking"
