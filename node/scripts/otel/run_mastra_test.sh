#!/bin/bash
# Run Mastra OTEL test

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_DIR="$SCRIPT_DIR/../.."
cd "$NODE_DIR"

echo ""
echo "================================================================================"
echo "Running Mastra OTEL Test"
echo "================================================================================"
echo ""

# Load environment variables from parent .env file
if [ -f "../.env" ]; then
    echo -e "${BLUE}📋 Loading environment variables from .env...${NC}"
    set -a
    source ../.env
    set +a
else
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "   Create one with:"
    echo "   OPENAI_API_KEY=sk-..."
    echo "   POSTHOG_API_KEY=phc_test"
    echo "   POSTHOG_HOST=http://localhost:8000"
    echo "   POSTHOG_PROJECT_ID=1"
    exit 1
fi

echo -e "${GREEN}✅ Environment loaded from .env${NC}"
echo ""

# Check if OpenAI API key is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}❌ OPENAI_API_KEY not set in .env${NC}"
    exit 1
fi

# Build TypeScript if needed
if [ ! -d "dist" ] || [ "scripts/otel/test_mastra_otel.ts" -nt "dist" ]; then
    echo -e "${YELLOW}🔨 Building TypeScript...${NC}"
    npm run build
    echo -e "${GREEN}✅ Build complete${NC}"
    echo ""
fi

# Run the test
echo -e "${BLUE}🚀 Running Mastra OTEL test...${NC}"
echo ""

npx tsx scripts/otel/test_mastra_otel.ts

echo ""
echo "================================================================================"
echo "Test complete!"
echo "================================================================================"
echo ""
echo -e "${BLUE}🔍 Check PostHog for traces:${NC}"
echo "   ${POSTHOG_HOST}/project/${POSTHOG_PROJECT_ID}/llm-analytics/traces"
echo ""
echo "Expected:"
echo "  - Service: mastra-otel-test"
echo "  - User ID: mastra-test-user"
echo "  - 4 conversation turns with tool calls"
echo ""
