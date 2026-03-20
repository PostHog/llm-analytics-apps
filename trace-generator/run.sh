#!/bin/bash

# Run the trace generator

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "🎯 Starting LLM Trace Generator..."
uv run trace-generator/trace_generator.py
