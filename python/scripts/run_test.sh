#!/bin/bash

# Script to run weather tool tests
# This reuses the same virtual environment as the main app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found. Run ./run.sh first to set up."
    exit 1
fi

# Run the test script
python scripts/test_weather_tool.py "$@"
