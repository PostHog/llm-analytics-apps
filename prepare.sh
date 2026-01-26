#!/bin/bash

# Unified prepare step for both Python and Node apps.
# - Loads .env
# - If POSTHOG_HOST is localhost, fetches current project api_token from local PostHog
# - Prompts to update .env if the token differs

# NOTE: This script is intended to be sourced from other scripts (". ../prepare.sh")
# so any exported variables are available to the caller. Avoid exiting the parent.

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
ENV_FILE="$ROOT_DIR/.env"

# Load existing env if present (so we can read POSTHOG_* values)
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

POSTHOG_HOST_VALUE="${POSTHOG_HOST:-}"
if [ -z "$POSTHOG_HOST_VALUE" ]; then
    # If not explicitly set, default to cloud; we only run for localhost
    POSTHOG_HOST_VALUE="https://app.posthog.com"
fi

# Only attempt localhost auto-key update when targeting local PostHog
if [ "$POSTHOG_HOST_VALUE" != "http://localhost:8010" ]; then
    # Nothing to do
    return 0 2>/dev/null || exit 0
fi

echo -e "${BLUE}🔧 Preparing environment for local PostHog...${NC}"

# Settings (override via env if desired)
PH_EMAIL="${POSTHOG_LOCAL_EMAIL:-test@posthog.com}"
PH_PASSWORD="${POSTHOG_LOCAL_PASSWORD:-12345678}"
PH_HOST="${POSTHOG_HOST_VALUE}"

tmp_cookie="$(mktemp 2>/dev/null || echo "/tmp/prepare_posthog_cookie_$$")"
trap 'rm -f "$tmp_cookie"' EXIT

# Login
login_payload=$(printf '{"email":"%s","password":"%s"}' "$PH_EMAIL" "$PH_PASSWORD")

login_status=$(curl -s -o /dev/null -w "%{http_code}" \
  -c "$tmp_cookie" \
  -H 'Content-Type: application/json' \
  -d "$login_payload" \
  "$PH_HOST/api/login" || echo "000")

if [ "$login_status" != "200" ]; then
    echo -e "${YELLOW}⚠️  Could not log in to ${PH_HOST} (status ${login_status}). Skipping key sync.${NC}"
    return 0 2>/dev/null || exit 0
fi

# Fetch current project
project_json=$(curl -s -b "$tmp_cookie" "$PH_HOST/api/projects/@current" || true)

if [ -z "$project_json" ]; then
    echo -e "${YELLOW}⚠️  Empty response from ${PH_HOST}/api/projects/@current. Skipping key sync.${NC}"
    return 0 2>/dev/null || exit 0
fi

# Extract api_token without requiring jq
LOCALHOST_KEY=$(printf "%s" "$project_json" | sed -n 's/.*"api_token"\s*:\s*"\([^"]*\)".*/\1/p' | head -n1)

if [ -z "$LOCALHOST_KEY" ]; then
    echo -e "${YELLOW}⚠️  Could not parse api_token from project response. Skipping key sync.${NC}"
    return 0 2>/dev/null || exit 0
fi

CURRENT_KEY="${POSTHOG_API_KEY:-}"

if [ -n "$CURRENT_KEY" ] && [ "$CURRENT_KEY" = "$LOCALHOST_KEY" ]; then
    echo -e "${GREEN}✅ POSTHOG_API_KEY already matches local instance${NC}"
    return 0 2>/dev/null || exit 0
fi

echo -e "${YELLOW}⚠️  Local PostHog API key differs from .env${NC}"
echo -e "   .env file:      ${CURRENT_KEY:-<unset>}"
echo -e "   localhost:      ${LOCALHOST_KEY}"
echo

read -p "Update .env with localhost key? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Ensure .env exists
    if [ ! -f "$ENV_FILE" ]; then
        touch "$ENV_FILE"
    fi

    # Update or append POSTHOG_API_KEY line
    if grep -q '^POSTHOG_API_KEY=' "$ENV_FILE"; then
        # macOS/BSD sed requires an extension for -i; create a .bak then remove
        sed -i.bak "s|^POSTHOG_API_KEY=.*|POSTHOG_API_KEY=${LOCALHOST_KEY}|" "$ENV_FILE"
        rm -f "$ENV_FILE.bak"
    else
        printf "\nPOSTHOG_API_KEY=%s\n" "$LOCALHOST_KEY" >> "$ENV_FILE"
    fi

    # Export in current shell (since we are sourced)
    export POSTHOG_API_KEY="$LOCALHOST_KEY"
    echo -e "${GREEN}✅ Updated .env and current shell with local API key${NC}"
else
    echo -e "${BLUE}ℹ️  Keeping existing .env API key${NC}"
fi

return 0 2>/dev/null || exit 0


