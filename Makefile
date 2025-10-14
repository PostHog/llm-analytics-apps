.PHONY: run-python run-node run-python-debug run-node-debug run-trace-generator run-trace-generator-debug

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

