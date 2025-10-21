#!/bin/bash

# Script to run weather tool tests
# This reuses the same node_modules as the main app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "❌ node_modules not found. Run ./run.sh first to set up."
    exit 1
fi

echo "✅ Dependencies found"

# Check if dist folder exists, build if not
if [ ! -d "dist" ]; then
    echo "📦 Building TypeScript..."
    npm run build
fi

# Run the test script with ts-node
npx ts-node --esm scripts/test_weather_tool.ts "$@"
