#!/usr/bin/env bash
set -euo pipefail

# Run AI provider examples from posthog-python and posthog-js repos.
# Uses the .env file from this repo for API keys.
#
# Usage:
#   ./run-examples.sh                           Interactive menu
#   ./run-examples.sh --list                    List all examples
#   ./run-examples.sh --all                     Run all examples sequentially
#   ./run-examples.sh --parallel                Run all examples in parallel (mprocs)
#   ./run-examples.sh --parallel anthropic      Run matching examples in parallel
#   ./run-examples.sh --install                 Install deps for all examples
#   ./run-examples.sh openai/embeddings         Run a specific example (fuzzy match)
#   ./run-examples.sh anthropic                 Run all examples matching "anthropic"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_REPO="${POSTHOG_PYTHON_PATH:-$SCRIPT_DIR/../posthog-python}"
JS_REPO="${POSTHOG_JS_PATH:-$SCRIPT_DIR/../posthog-js}"

# Load .env
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Find Python: prefer the posthog-python venv, fall back to system python3
if [[ -x "$PYTHON_REPO/.venv/bin/python" ]]; then
    PYTHON="$PYTHON_REPO/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

install_python_deps() {
    echo "Installing Python example dependencies..."

    if ! command -v uv &>/dev/null; then
        echo "  uv is required to install Python example dependencies."
        echo "  Install it: https://docs.astral.sh/uv/getting-started/installation/"
        return 1
    fi

    for dir in "$PYTHON_REPO"/examples/example-ai-*/; do
        [[ -d "$dir" ]] || continue
        local name
        name=$(basename "$dir")
        if [[ -f "$dir/pyproject.toml" ]]; then
            echo "  $name..."
            (cd "$dir" && uv sync 2>&1 | tail -1)
        fi
    done
    echo "  Done."
}

install_node_deps() {
    echo "Installing Node.js example dependencies..."
    for dir in "$JS_REPO"/examples/example-ai-*/; do
        [[ -d "$dir" ]] || continue
        local name
        name=$(basename "$dir")
        if [[ -f "$dir/package.json" ]]; then
            echo "  $name..."
            (cd "$dir" && pnpm install 2>&1 | tail -1)
        fi
    done
    echo "  Done."
}

# ---------------------------------------------------------------------------
# Discover examples
# ---------------------------------------------------------------------------

# Parallel arrays: NAMES[i] is the key, FILES[i] is the path, LANGS[i] is py/ts
declare -a NAMES=()
declare -a FILES=()
declare -a LANGS=()

discover_python() {
    for dir in "$PYTHON_REPO"/examples/example-ai-*/; do
        [[ -d "$dir" ]] || continue
        local group
        group=$(basename "$dir" | sed 's/^example-ai-//')
        for file in "$dir"/*.py; do
            [[ -f "$file" ]] || continue
            local base
            base=$(basename "$file" .py)
            NAMES+=("python/$group/$base")
            FILES+=("$file")
            LANGS+=("py")
        done
    done
}

discover_node() {
    for dir in "$JS_REPO"/examples/example-ai-*/; do
        [[ -d "$dir" ]] || continue
        local group
        group=$(basename "$dir" | sed 's/^example-ai-//')
        for file in "$dir"/*.ts; do
            [[ -f "$file" ]] || continue
            local base
            base=$(basename "$file" .ts)
            NAMES+=("node/$group/$base")
            FILES+=("$file")
            LANGS+=("ts")
        done
    done
}

# ---------------------------------------------------------------------------
# Run an example
# ---------------------------------------------------------------------------

run_example() {
    local idx="$1"
    local file="${FILES[$idx]}"
    local lang="${LANGS[$idx]}"
    local name="${NAMES[$idx]}"
    local dir
    dir=$(dirname "$file")

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [[ "$lang" == "py" ]]; then
        if [[ -f "$dir/pyproject.toml" ]] && command -v uv &>/dev/null; then
            (cd "$dir" && uv run python "$(basename "$file")")
        else
            "$PYTHON" "$file"
        fi
    else
        (cd "$dir" && npx tsx "$(basename "$file")")
    fi
}

# Build the shell command string for a single example (used by mprocs)
example_cmd() {
    local idx="$1"
    local file="${FILES[$idx]}"
    local lang="${LANGS[$idx]}"
    local dir
    dir=$(dirname "$file")

    if [[ "$lang" == "py" ]]; then
        if [[ -f "$dir/pyproject.toml" ]] && command -v uv &>/dev/null; then
            echo "cd $dir && uv run python $(basename "$file")"
        else
            echo "$PYTHON $file"
        fi
    else
        echo "cd $dir && npx tsx $(basename "$file")"
    fi
}

# Find examples matching a pattern. Returns matching indices in MATCHED array.
find_matches() {
    local pattern="$1"
    MATCHED=()
    for i in "${!NAMES[@]}"; do
        if [[ "${NAMES[$i]}" == *"$pattern"* ]]; then
            MATCHED+=("$i")
        fi
    done
}

# ---------------------------------------------------------------------------
# Parallel execution with mprocs
# ---------------------------------------------------------------------------

run_parallel() {
    local indices=("$@")

    if ! command -v mprocs &>/dev/null; then
        echo "mprocs is not installed. Install it with: brew install mprocs"
        exit 1
    fi

    # Build mprocs config
    local config
    config=$(mktemp /tmp/mprocs-examples-XXXXXX.yaml)
    trap "rm -f $config" EXIT

    echo "procs:" > "$config"
    for i in "${indices[@]}"; do
        local name="${NAMES[$i]}"
        local cmd
        cmd=$(example_cmd "$i")
        # Wrap in env-loading shell so each proc has the API keys
        local full_cmd="set -a; source $SCRIPT_DIR/.env 2>/dev/null; set +a; $cmd"
        echo "  \"$name\":" >> "$config"
        echo "    shell: \"$full_cmd\"" >> "$config"
    done

    echo "Running ${#indices[@]} examples in parallel..."
    mprocs --config "$config"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Handle --install before discovering examples
if [[ "${1:-}" == "--install" ]]; then
    install_python_deps
    echo ""
    install_node_deps
    exit 0
fi

discover_python
discover_node

if [[ ${#NAMES[@]} -eq 0 ]]; then
    echo "No examples found."
    echo "Expected posthog-python at: $PYTHON_REPO"
    echo "Expected posthog-js at:     $JS_REPO"
    echo ""
    echo "Set POSTHOG_PYTHON_PATH or POSTHOG_JS_PATH to override."
    exit 1
fi

MODE="${1:-}"

if [[ "$MODE" == "--parallel" ]]; then
    FILTER="${2:-}"
    if [[ -n "$FILTER" ]]; then
        find_matches "$FILTER"
        if [[ ${#MATCHED[@]} -eq 0 ]]; then
            echo "No examples matching '$FILTER'."
            exit 1
        fi
        run_parallel "${MATCHED[@]}"
    else
        # All examples
        ALL_INDICES=()
        for i in "${!NAMES[@]}"; do
            ALL_INDICES+=("$i")
        done
        run_parallel "${ALL_INDICES[@]}"
    fi

elif [[ "$MODE" == "--all" ]]; then
    echo "Running all ${#NAMES[@]} examples..."
    FAILED=0
    PASSED=0
    for i in "${!NAMES[@]}"; do
        if run_example "$i"; then
            (( PASSED++ )) || true
        else
            (( FAILED++ )) || true
            echo "FAILED: ${NAMES[$i]}"
        fi
    done
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Results: $PASSED passed, $FAILED failed (${#NAMES[@]} total)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit $FAILED

elif [[ "$MODE" == "--list" ]]; then
    echo "Available examples:"
    echo ""
    for name in "${NAMES[@]}"; do
        echo "  $name"
    done
    echo ""
    echo "${#NAMES[@]} examples found."

elif [[ -n "$MODE" && "$MODE" != --* ]]; then
    # Name-based matching
    find_matches "$MODE"
    if [[ ${#MATCHED[@]} -eq 0 ]]; then
        echo "No examples matching '$MODE'."
        echo ""
        echo "Use --list to see all available examples."
        exit 1
    elif [[ ${#MATCHED[@]} -eq 1 ]]; then
        run_example "${MATCHED[0]}"
    else
        echo "Running ${#MATCHED[@]} examples matching '$MODE':"
        for i in "${MATCHED[@]}"; do
            echo "  ${NAMES[$i]}"
        done
        for i in "${MATCHED[@]}"; do
            run_example "$i" || echo "FAILED: ${NAMES[$i]}"
        done
    fi

else
    # Interactive menu
    echo ""
    echo "AI Provider Examples"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    for name in "${NAMES[@]}"; do
        echo "  $name"
    done
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Type a name (or partial match) to run, 'a' for all, or 'q' to quit."
    echo ""

    while true; do
        read -rp "> " CHOICE
        case "$CHOICE" in
            q|Q) echo "Bye."; exit 0 ;;
            a|A)
                for i in "${!NAMES[@]}"; do
                    run_example "$i" || echo "FAILED: ${NAMES[$i]}"
                done
                ;;
            "")
                continue
                ;;
            *)
                find_matches "$CHOICE"
                if [[ ${#MATCHED[@]} -eq 0 ]]; then
                    echo "No match for '$CHOICE'. Try again."
                else
                    if [[ ${#MATCHED[@]} -gt 1 ]]; then
                        echo "Matched ${#MATCHED[@]} examples:"
                        for i in "${MATCHED[@]}"; do
                            echo "  ${NAMES[$i]}"
                        done
                    fi
                    for i in "${MATCHED[@]}"; do
                        run_example "$i" || echo "FAILED: ${NAMES[$i]}"
                    done
                fi
                ;;
        esac
        echo ""
    done
fi
