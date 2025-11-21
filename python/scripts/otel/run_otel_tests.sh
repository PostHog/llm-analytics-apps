#!/bin/bash
# Run all three conversation test methods and compare results

# Don't exit on errors - we want to run all tests even if one fails
set +e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/../../.."

# Activate virtual environment
source python/venv/bin/activate

echo "================================================================================"
echo "Running all conversation tests (SDK, OTEL v1, OTEL v2)"
echo "================================================================================"
echo

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "   Create one with:"
    echo "   OPENAI_API_KEY=sk-..."
    echo "   POSTHOG_API_KEY=phc_test"
    echo "   POSTHOG_HOST=http://localhost:8000"
    echo "   POSTHOG_PROJECT_ID=1"
    exit 1
fi

# Source environment
set -a
source .env
set +a

echo "✅ Environment loaded from .env"
echo

# Run SDK test
echo "================================================================================"
echo "1/3: PostHog SDK Test"
echo "================================================================================"
python python/scripts/otel/test_openai_otel_ph_sdk.py
echo
sleep 2

# Run OTEL v1 test
echo "================================================================================"
echo "2/3: OTEL v1 Test"
echo "================================================================================"
python python/scripts/otel/test_openai_otel_v1.py
echo
sleep 2

# Run OTEL v2 test
echo "================================================================================"
echo "3/3: OTEL v2 Test (testing message accumulation fix)"
echo "================================================================================"
python python/scripts/otel/test_openai_otel_v2.py
echo

echo "================================================================================"
echo "All tests complete!"
echo "================================================================================"
echo
echo "🔍 Compare results in ClickHouse:"
echo
echo "docker exec -it posthog-clickhouse-1 clickhouse-client --query \""
echo "SELECT "
echo "    event,"
echo "    JSONExtractString(properties, '\$ai_trace_id') as trace_id,"
echo "    JSONExtractString(properties, '\$ai_input') as input,"
echo "    arrayJoin(splitByString('}, {', input)) as msg"
echo "FROM sharded_events"
echo "WHERE team_id = 1"
echo "  AND timestamp >= now() - INTERVAL 10 MINUTE"
echo "  AND event = '\$ai_generation'"
echo "ORDER BY timestamp DESC"
echo "LIMIT 20"
echo "FORMAT Vertical\""
echo
echo "Expected results:"
echo "  - SDK: Each turn = separate event, no history accumulation"
echo "  - v1: Each turn = separate event with FULL conversation history in span"
echo "  - v2: Each turn = separate event with FULL conversation history (if fix works!)"
echo
echo "Look for Turn 4 (message: 'Thanks, bye!') in each method:"
echo "  - Should see ALL previous messages in \$ai_input, not just 'Thanks, bye!'"
echo
