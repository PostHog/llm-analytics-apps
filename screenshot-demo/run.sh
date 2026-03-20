#!/bin/bash
# Run the Screenshot Demo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

uv run screenshot-demo/screenshot_demo.py "$@"
