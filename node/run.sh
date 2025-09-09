#!/bin/bash

# Unified AI Chatbot Runner
# This script sets up the node environment, installs dependencies, and runs the chatbot

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables from parent .env file
if [ -f "../.env" ]; then
    echo -e "${BLUE}📋 Loading environment variables from .env...${NC}"
    set -a
    source ../.env
    set +a 
fi


echo -e "${BLUE}🚀 Unified AI Chatbot Setup${NC}"
echo "=================================="

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js is not installed or not in PATH${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Checking Node.js version...${NC}"
node --version

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ npm is not installed or not in PATH${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Checking npm version...${NC}"
npm --version

# Check if using local PostHog packages or npm packages
if [ -n "$POSTHOG_JS_PATH" ]; then
    echo -e "${YELLOW}📦 Using local PostHog packages from: $POSTHOG_JS_PATH${NC}"
    
    POSTHOG_AI_DIR="$POSTHOG_JS_PATH/packages/ai"
    POSTHOG_NODE_DIR="$POSTHOG_JS_PATH/packages/node"
    
    # Rebuild local packages if they exist
    if [ -d "$POSTHOG_AI_DIR" ]; then
        echo -e "${YELLOW}🔧 Rebuilding local @posthog/ai package...${NC}"
        (cd "$POSTHOG_AI_DIR" && npm run build)
        echo -e "${GREEN}✅ @posthog/ai package rebuilt${NC}"
    fi
    
    if [ -d "$POSTHOG_NODE_DIR" ]; then
        echo -e "${YELLOW}🔧 Rebuilding local posthog-node package...${NC}"
        (cd "$POSTHOG_NODE_DIR" && npm run build)
        echo -e "${GREEN}✅ posthog-node package rebuilt${NC}"
    fi
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}📦 Installing dependencies...${NC}"
        npm install
    fi
    
    # Remove any existing PostHog packages to ensure clean install
    echo -e "${YELLOW}🧹 Removing existing PostHog packages...${NC}"
    rm -rf node_modules/@posthog/ai node_modules/posthog-node
    
    # Install/update local packages without saving to package.json
    echo -e "${YELLOW}🔄 Installing local PostHog packages...${NC}"
    npm install --no-save "$POSTHOG_AI_DIR" "$POSTHOG_NODE_DIR"
    
elif [ -n "$POSTHOG_JS_AI_VERSION" ] || [ -n "$POSTHOG_JS_NODE_VERSION" ]; then
    echo -e "${YELLOW}📦 Installing specific PostHog versions${NC}"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
        echo -e "${YELLOW}📦 Installing dependencies...${NC}"
        npm install
    fi
    
    # Remove any existing PostHog packages to ensure clean install
    echo -e "${YELLOW}🧹 Removing existing PostHog packages...${NC}"
    rm -rf node_modules/@posthog/ai node_modules/posthog-node
    
    # Install specific versions
    PACKAGES=""
    if [ -n "$POSTHOG_JS_AI_VERSION" ]; then
        echo -e "${YELLOW}  Installing @posthog/ai@$POSTHOG_JS_AI_VERSION${NC}"
        PACKAGES="$PACKAGES @posthog/ai@$POSTHOG_JS_AI_VERSION"
    else
        PACKAGES="$PACKAGES @posthog/ai"
    fi
    
    if [ -n "$POSTHOG_JS_NODE_VERSION" ]; then
        echo -e "${YELLOW}  Installing posthog-node@$POSTHOG_JS_NODE_VERSION${NC}"
        PACKAGES="$PACKAGES posthog-node@$POSTHOG_JS_NODE_VERSION"
    else
        PACKAGES="$PACKAGES posthog-node"
    fi
    
    npm install --no-save $PACKAGES
    
else
    # Standard installation from package.json
    echo -e "${YELLOW}📦 Installing dependencies from package.json...${NC}"
    
    # Check if we need to clean up from previous local or version-specific installs
    NEED_REINSTALL=false
    
    # Remove any locally installed PostHog packages if they exist (from previous local dev)
    if [ -L "node_modules/@posthog/ai" ] || [ -L "node_modules/posthog-node" ]; then
        echo -e "${YELLOW}🧹 Removing local PostHog package symlinks...${NC}"
        rm -rf node_modules/@posthog/ai node_modules/posthog-node
        NEED_REINSTALL=true
    fi
    
    # Check if packages were installed with specific versions (not matching package.json)
    if [ -d "node_modules/@posthog/ai" ] && [ -d "node_modules/posthog-node" ]; then
        # Get installed versions
        INSTALLED_AI_VERSION=$(node -p "require('./node_modules/@posthog/ai/package.json').version" 2>/dev/null || echo "unknown")
        INSTALLED_NODE_VERSION=$(node -p "require('./node_modules/posthog-node/package.json').version" 2>/dev/null || echo "unknown")
        
        # Get expected versions from package.json (remove ^ or ~ prefix)
        EXPECTED_AI_VERSION=$(node -p "require('./package.json').dependencies['@posthog/ai'].replace(/^[\^~]/, '')" 2>/dev/null || echo "unknown")
        EXPECTED_NODE_VERSION=$(node -p "require('./package.json').dependencies['posthog-node'].replace(/^[\^~]/, '')" 2>/dev/null || echo "unknown")
        
        # If versions don't match (and we're not using ^ or ~ ranges), reinstall
        if [ "$INSTALLED_AI_VERSION" != "$EXPECTED_AI_VERSION" ] || [ "$INSTALLED_NODE_VERSION" != "$EXPECTED_NODE_VERSION" ]; then
            echo -e "${YELLOW}🧹 Installed versions don't match package.json, reinstalling...${NC}"
            rm -rf node_modules/@posthog/ai node_modules/posthog-node
            NEED_REINSTALL=true
        fi
    fi
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ] || [ "$NEED_REINSTALL" = true ]; then
        if [ "$NEED_REINSTALL" = true ]; then
            # Just reinstall the PostHog packages
            echo -e "${YELLOW}🔄 Reinstalling PostHog packages from package.json...${NC}"
            npm install @posthog/ai posthog-node
        else
            # Full install
            npm install
        fi
    else
        # Check if PostHog packages exist and have dist folders
        if [ ! -d "node_modules/@posthog/ai/dist" ] || [ ! -d "node_modules/posthog-node/dist" ]; then
            echo -e "${YELLOW}🔄 Reinstalling PostHog packages from npm...${NC}"
            npm install @posthog/ai posthog-node
        else
            echo -e "${GREEN}✅ Dependencies already installed${NC}"
        fi
    fi
fi

# Build TypeScript files
echo -e "${YELLOW}🔨 Building TypeScript files...${NC}"
npm run build

echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""

# Clear terminal only after successful setup
clear

echo -e "${BLUE}🤖 Starting Unified AI Chatbot...${NC}"
echo ""

# Run the main application
node dist/index.js