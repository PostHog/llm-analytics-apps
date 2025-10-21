.PHONY: run-python run-node run-python-debug run-node-debug run-trace-generator run-trace-generator-debug python-install python-install-reset python-install-local

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

