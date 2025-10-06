#!/bin/bash

# Unified AI Chatbot Runner
# This script sets up the virtual environment, installs dependencies, and runs the chatbot

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
    set -a
    source ../.env
    set +a
fi

echo -e "${BLUE}🚀 Unified AI Chatbot Setup${NC}"
echo "=================================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed or not in PATH${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Checking Python version...${NC}"
python3 --version

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}🔧 Creating virtual environment...${NC}"
    python3 -m venv venv
else
    echo -e "${GREEN}✅ Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}🔌 Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}⬆️  Upgrading pip...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "${YELLOW}📦 Installing dependencies...${NC}"

# Check if using local paths or package versions
if [ -n "$POSTHOG_PYTHON_PATH" ] || [ -n "$LITELLM_PATH" ]; then
    # Install other requirements first (excluding packages we'll install locally)
    requirements_filter="requirements.txt"
    
    if [ -n "$POSTHOG_PYTHON_PATH" ]; then
        echo -e "${YELLOW}📦 Using local posthog-python from: $POSTHOG_PYTHON_PATH${NC}"
        requirements_filter=$(grep -v "posthog-python" requirements.txt | grep -v "^posthog" | grep -v "^-e")
    fi
    
    if [ -n "$LITELLM_PATH" ]; then
        echo -e "${YELLOW}📦 Using local litellm from: $LITELLM_PATH${NC}"
        requirements_filter=$(echo "$requirements_filter" | grep -v "litellm")
    fi
    
    # Install filtered requirements
    echo "$requirements_filter" | pip install -r /dev/stdin
    
    # Install local packages as editable
    if [ -n "$POSTHOG_PYTHON_PATH" ]; then
        pip install -e "$POSTHOG_PYTHON_PATH"
    fi
    
    if [ -n "$LITELLM_PATH" ]; then
        pip install -e "$LITELLM_PATH"
    fi
    
elif [ -n "$POSTHOG_PYTHON_VERSION" ]; then
    echo -e "${YELLOW}📦 Installing specific posthog version: $POSTHOG_PYTHON_VERSION${NC}"
    # Install other requirements first
    grep -v "^posthog" requirements.txt | pip install -r /dev/stdin
    # Then install specific version
    pip install posthog==$POSTHOG_PYTHON_VERSION
else
    echo -e "${YELLOW}📦 Installing dependencies from requirements.txt${NC}"
    pip install -r requirements.txt
fi

echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""

# Clear terminal only after successful setup
clear

echo -e "${BLUE}🤖 Starting Unified AI Chatbot...${NC}"
echo ""

# Run the main application
python main.py

# Deactivate virtual environment when done
deactivate