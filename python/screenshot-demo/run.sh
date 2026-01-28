#!/bin/bash
# Run the Screenshot Demo

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(dirname "$SCRIPT_DIR")"

# Check for DEBUG environment variable
if [ -z "$DEBUG" ]; then
    # Load from .env file if not set
    if [ -f "$PYTHON_DIR/../.env" ]; then
        export $(grep -E '^DEBUG=' "$PYTHON_DIR/../.env" | xargs)
    fi
fi

# Check if virtual environment exists
if [ ! -d "$PYTHON_DIR/venv" ]; then
    echo "Virtual environment not found. Please run the main Python app first:"
    echo "  cd $PYTHON_DIR && ./run.sh"
    exit 1
fi

# Activate virtual environment
source "$PYTHON_DIR/venv/bin/activate"

# Run the screenshot demo
cd "$SCRIPT_DIR"
python screenshot_demo.py "$@"
