#!/bin/bash

# Ingest a trace JSON file into local PostHog using the python venv
# Usage: ./ingest_trace.sh [path/to/trace.json]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if python venv exists
if [ ! -d "python/venv" ]; then
    echo -e "${YELLOW}⚠️  Python venv not found. Setting it up...${NC}"
    cd python
    INSTALL_ONLY=1 ./run.sh
    cd ..
    echo -e "${GREEN}✅ Python venv ready!${NC}"
    echo ""
fi

# Activate the python venv
source python/venv/bin/activate

# Run the ingestion script
python3 ingest_trace.py "$@"

# Deactivate venv
deactivate
