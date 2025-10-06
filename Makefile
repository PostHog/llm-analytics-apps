.PHONY: run-python run-node run-python-debug run-node-debug

run-python:
	@cd python && ./run.sh

run-node:
	@cd node && ./run.sh

run-python-debug:
	@cd python && DEBUG=1 ./run.sh

run-node-debug:
	@cd node && DEBUG=1 ./run.sh

