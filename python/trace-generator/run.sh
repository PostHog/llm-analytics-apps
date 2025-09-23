#!/bin/bash

# Script to run the trace generator with virtual environment
# Works from any directory

set -e  # Exit on any error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Find and activate the virtual environment
if [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
elif [ -f "../../venv/bin/activate" ]; then
    source ../../venv/bin/activate
else
    echo "❌ Virtual environment not found. Please run python/run.sh first to set up the environment."
    exit 1
fi

echo "🎯 Starting LLM Trace Generator..."
python trace_generator.py