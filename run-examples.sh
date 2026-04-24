#!/usr/bin/env bash
set -euo pipefail

# Run AI provider examples from posthog-python and posthog-js repos.
# Uses the .env file from this repo for API keys.
#
# Results are cached in .results/ — examples that passed with the same file
# content are skipped on subsequent runs to save API costs.
#
# Usage:
#   ./run-examples.sh                           Interactive menu
#   ./run-examples.sh --list                    List all examples (with cache status)
#   ./run-examples.sh --all                     Run all examples sequentially
#   ./run-examples.sh --parallel                Run all examples in parallel (phrocs)
#   ./run-examples.sh --parallel anthropic      Run matching examples in parallel
#   ./run-examples.sh --install                 Install deps for all examples
#   ./run-examples.sh --rerun                   Force re-run (ignore cache), combinable with other flags
#   ./run-examples.sh --reset                   Clear the results cache
#   ./run-examples.sh openai/embeddings         Run a specific example (fuzzy match, bypasses cache)
#   ./run-examples.sh anthropic                 Run all examples matching "anthropic"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_REPO="${POSTHOG_PYTHON_PATH:-$SCRIPT_DIR/../posthog-python}"
JS_REPO="${POSTHOG_JS_PATH:-$SCRIPT_DIR/../posthog-js}"
RESULTS_DIR="$SCRIPT_DIR/.results"

# Load .env
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# ---------------------------------------------------------------------------
# Parse --rerun flag from anywhere in argv
# ---------------------------------------------------------------------------

RERUN=0
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--rerun" ]]; then
        RERUN=1
    else
        ARGS+=("$arg")
    fi
done
set -- ${ARGS[@]+"${ARGS[@]}"}

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
# Results cache
# ---------------------------------------------------------------------------

cache_key() {
    local name="$1"
    echo "${name//\//__}"
}

# Associative array of file path → hash, populated by precompute_hashes
declare -A FILE_HASHES=()

file_hash() {
    local file="$1"
    if [[ -n "${FILE_HASHES[$file]+x}" ]]; then
        echo "${FILE_HASHES[$file]}"
    else
        shasum -a 256 "$file" | cut -d' ' -f1
    fi
}

# Compute all example file hashes in a single shasum call
precompute_hashes() {
    [[ ${#FILES[@]} -eq 0 ]] && return
    while IFS=' ' read -r hash filepath; do
        FILE_HASHES["$filepath"]="$hash"
    done < <(shasum -a 256 "${FILES[@]}")
}

is_cached() {
    local idx="$1"
    [[ "$RERUN" == "0" ]] || return 1
    local key
    key=$(cache_key "${NAMES[$idx]}")
    local cache_file="$RESULTS_DIR/$key.hash"
    [[ -f "$cache_file" ]] || return 1
    local cached_hash current_hash
    cached_hash=$(cat "$cache_file")
    current_hash=$(file_hash "${FILES[$idx]}")
    [[ "$cached_hash" == "$current_hash" ]]
}

mark_passed() {
    local idx="$1"
    mkdir -p "$RESULTS_DIR"
    local key
    key=$(cache_key "${NAMES[$idx]}")
    file_hash "${FILES[$idx]}" > "$RESULTS_DIR/$key.hash"
}

mark_failed() {
    local idx="$1"
    local key
    key=$(cache_key "${NAMES[$idx]}")
    rm -f "$RESULTS_DIR/$key.hash"
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

    if is_cached "$idx"; then
        echo "  ✓ $name (cached)"
        return 0
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    local rc=0
    if [[ "$lang" == "py" ]]; then
        if [[ -f "$dir/pyproject.toml" ]] && command -v uv &>/dev/null; then
            (cd "$dir" && uv run python "$(basename "$file")") || rc=$?
        else
            "$PYTHON" "$file" || rc=$?
        fi
    else
        (cd "$dir" && npx tsx "$(basename "$file")") || rc=$?
    fi

    if [[ $rc -eq 0 ]]; then
        mark_passed "$idx"
    else
        mark_failed "$idx"
    fi
    return $rc
}

# Build the shell command string for a single example (used by phrocs)
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
# Parallel execution with phrocs
# ---------------------------------------------------------------------------

run_parallel() {
    local indices=("$@")

    if ! command -v phrocs &>/dev/null; then
        echo "phrocs is not installed. Install it with: brew tap posthog/tap && brew install phrocs"
        exit 1
    fi

    # Filter out cached examples
    local filtered=()
    local skipped=0
    for i in "${indices[@]}"; do
        if is_cached "$i"; then
            (( skipped++ )) || true
        else
            filtered+=("$i")
        fi
    done

    if [[ ${#filtered[@]} -eq 0 ]]; then
        echo "All ${#indices[@]} examples cached. Use --rerun to force re-running."
        return 0
    fi

    mkdir -p "$RESULTS_DIR"

    # Build phrocs config
    local config info_script
    config=$(mktemp /tmp/phrocs-examples-XXXXXX.yaml)
    info_script=$(mktemp /tmp/phrocs-info-XXXXXX.sh)
    trap "rm -f $config $info_script" EXIT

    local total=${#indices[@]}
    local cached=$skipped
    local pending=${#filtered[@]}

    # Info tab script with PostHog brand colors
    cat > "$info_script" <<'INFOEOF'
#!/usr/bin/env bash
o='\033[38;2;245;78;0m'  # orange #F54E00
b='\033[38;2;29;74;255m' # blue   #1D4AFF
g='\033[38;5;245m'       # gray
B='\033[1m'              # bold
r='\033[0m'              # reset
INFOEOF
    cat >> "$info_script" <<INFOEOF
echo ''
printf "\${o}\${B}  PostHog LLM Analytics — Provider Examples\${r}\\n"
printf "\${g}  ─────────────────────────────────────\${r}\\n"
echo ''
printf "  \${B}Examples:\${r}  \${b}${pending}\${r} running, \${b}${cached}\${r} cached, \${b}${total}\${r} total\\n"
echo ''
printf "  Cached examples are skipped because their source\\n"
printf "  has not changed since the last successful run.\\n"
echo ''
printf "\${g}  ─────────────────────────────────────\${r}\\n"
printf "  \${B}Commands:\${r}\\n"
printf "    \${b}--rerun\${r}    Ignore cache and re-run everything\\n"
printf "    \${b}--reset\${r}    Clear the results cache\\n"
printf "    \${b}--list\${r}     Show all examples with cache status\\n"
echo ''
printf "\${g}  ─────────────────────────────────────\${r}\\n"
echo ''
INFOEOF
    chmod +x "$info_script"

    echo "procs:" > "$config"
    echo "  info:" >> "$config"
    echo "    shell: \"bash $info_script\"" >> "$config"

    for i in "${filtered[@]}"; do
        local name="${NAMES[$i]}"
        local cmd
        cmd=$(example_cmd "$i")
        local key
        key=$(cache_key "$name")
        local hash
        hash=$(file_hash "${FILES[$i]}")
        local cache_file="$RESULTS_DIR/$key.hash"
        # Wrap command to record pass/fail in the results cache
        local full_cmd="set -a; source $SCRIPT_DIR/.env 2>/dev/null; set +a; ($cmd) && printf '%s' '$hash' > '$cache_file' || { rm -f '$cache_file'; exit 1; }"
        echo "  \"$name\":" >> "$config"
        echo "    shell: \"$full_cmd\"" >> "$config"
    done

    phrocs --config "$config"
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

# Handle --reset before discovering examples
if [[ "${1:-}" == "--reset" ]]; then
    if [[ -d "$RESULTS_DIR" ]]; then
        rm -rf "$RESULTS_DIR"
        echo "Results cache cleared."
    else
        echo "No results cache to clear."
    fi
    exit 0
fi

discover_python
discover_node
precompute_hashes

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
    echo "Running ${#NAMES[@]} examples..."
    if [[ "$RERUN" == "0" ]]; then
        echo "(use --rerun to ignore cache)"
    fi
    echo ""
    FAILED=0
    PASSED=0
    SKIPPED=0
    for i in "${!NAMES[@]}"; do
        was_cached=0
        is_cached "$i" && was_cached=1
        if run_example "$i"; then
            if [[ $was_cached -eq 1 ]]; then
                (( SKIPPED++ )) || true
            else
                (( PASSED++ )) || true
            fi
        else
            (( FAILED++ )) || true
            echo "FAILED: ${NAMES[$i]}"
        fi
    done
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    summary="Results: $PASSED passed, $FAILED failed"
    if [[ $SKIPPED -gt 0 ]]; then
        summary="$summary, $SKIPPED cached"
    fi
    echo "$summary (${#NAMES[@]} total)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit $FAILED

elif [[ "$MODE" == "--list" ]]; then
    echo "Available examples:"
    echo ""
    cached_count=0
    for i in "${!NAMES[@]}"; do
        if is_cached "$i"; then
            echo "  ✓ ${NAMES[$i]}"
            (( cached_count++ )) || true
        else
            echo "    ${NAMES[$i]}"
        fi
    done
    echo ""
    if [[ $cached_count -gt 0 ]]; then
        echo "${#NAMES[@]} examples found ($cached_count cached, $((${#NAMES[@]} - cached_count)) pending)."
    else
        echo "${#NAMES[@]} examples found."
    fi

elif [[ -n "$MODE" && "$MODE" != --* ]]; then
    # Name-based matching
    find_matches "$MODE"
    if [[ ${#MATCHED[@]} -eq 0 ]]; then
        echo "No examples matching '$MODE'."
        echo ""
        echo "Use --list to see all available examples."
        exit 1
    elif [[ ${#MATCHED[@]} -eq 1 ]]; then
        # Running a single example directly always bypasses the cache.
        RERUN=1
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
    for i in "${!NAMES[@]}"; do
        if is_cached "$i"; then
            echo "  ✓ ${NAMES[$i]}"
        else
            echo "    ${NAMES[$i]}"
        fi
    done
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Type a name (or partial match) to run, 'a' for all, or 'q' to quit."
    echo "✓ = cached (will be skipped). Use --rerun to force."
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
