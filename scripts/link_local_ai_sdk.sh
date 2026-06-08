#!/usr/bin/env bash
# Builds @posthog/ai from a local posthog-js checkout and links it (plus the
# matching posthog-node) into this repo, so the Node scripts run against an
# unreleased SDK build instead of the published version pinned in package.json.
#
#   ./scripts/link_local_ai_sdk.sh                       # uses ../posthog-js
#   POSTHOG_JS_PATH=/path/to/posthog-js ./scripts/link_local_ai_sdk.sh
#
# This rewrites package.json's @posthog/ai / posthog-node entries to link: paths
# (a local-only change — don't commit it). Restore the published versions with:
#   git checkout -- package.json pnpm-lock.yaml && pnpm install
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JS_PATH="$(cd "${POSTHOG_JS_PATH:-$REPO_ROOT/../posthog-js}" 2>/dev/null && pwd || true)"

if [ -z "$JS_PATH" ] || [ ! -d "$JS_PATH/packages/ai" ]; then
  echo "error: @posthog/ai not found under '${POSTHOG_JS_PATH:-../posthog-js}'." >&2
  echo "Set POSTHOG_JS_PATH to your local posthog-js checkout." >&2
  exit 1
fi

echo "==> Building @posthog/ai (and workspace deps) in $JS_PATH"
( cd "$JS_PATH" && CI=true pnpm --filter "@posthog/ai..." build )

echo "==> Linking @posthog/ai + posthog-node from $JS_PATH into $REPO_ROOT"
( cd "$REPO_ROOT" && pnpm add \
  "@posthog/ai@link:$JS_PATH/packages/ai" \
  "posthog-node@link:$JS_PATH/packages/node" )

echo "==> Done. package.json now links to your local build (don't commit it)."
echo "    Restore the published SDK with:"
echo "    git checkout -- package.json pnpm-lock.yaml && pnpm install"
