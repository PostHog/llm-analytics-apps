"""
Test script for OpenTelemetry v2 instrumentation with PostHog.

This script sends a simple OpenAI request and checks if logs are being sent
to the PostHog OTLP logs endpoint.
"""

import os
import time
from openai import OpenAI
from opentelemetry import _events, _logs, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk._events import EventLoggerProvider

# Configuration - using environment variables
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8000")
POSTHOG_PROJECT_ID = os.getenv("POSTHOG_PROJECT_ID", "1")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not POSTHOG_API_KEY:
    print("❌ POSTHOG_API_KEY not set")
    exit(1)

if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY not set")
    exit(1)

print("=" * 60)
print("OpenTelemetry v2 Logs Test")
print("=" * 60)
print(f"PostHog Host: {POSTHOG_HOST}")
print(f"Project ID: {POSTHOG_PROJECT_ID}")
print(f"API Key: {POSTHOG_API_KEY[:10]}...")
print()

# Create resource
resource = Resource.create({
    "service.name": "test-otel-v2-logs",
    "service.version": "1.0.0",
})

# Setup traces exporter
traces_endpoint = f"{POSTHOG_HOST}/api/projects/{POSTHOG_PROJECT_ID}/ai/otel/v1/traces"
print(f"📤 Traces endpoint: {traces_endpoint}")
tracer_provider = TracerProvider(resource=resource)
trace_exporter = OTLPSpanExporter(
    endpoint=traces_endpoint,
    headers={"Authorization": f"Bearer {POSTHOG_API_KEY}"},
)
tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
trace.set_tracer_provider(tracer_provider)

# Setup logs exporter
logs_endpoint = f"{POSTHOG_HOST}/api/projects/{POSTHOG_PROJECT_ID}/ai/otel/v1/logs"
print(f"📤 Logs endpoint: {logs_endpoint}")
logger_provider = LoggerProvider(resource=resource)
log_exporter = OTLPLogExporter(
    endpoint=logs_endpoint,
    headers={"Authorization": f"Bearer {POSTHOG_API_KEY}"},
)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
_logs.set_logger_provider(logger_provider)

# Configure event logger provider (v2 uses Events API which wraps Logs API)
event_logger_provider = EventLoggerProvider(logger_provider=logger_provider)
_events.set_event_logger_provider(event_logger_provider)
print(f"✅ Event logger provider configured")

# Enable message content capture
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
print(f"✅ Message content capture enabled")
print()

# Instrument OpenAI
OpenAIInstrumentor().instrument()
print("✅ OpenAI instrumented with v2")
print()

# Create OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Make a simple test call
print("📞 Making OpenAI API call...")
print("-" * 60)

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_completion_tokens=50,
        messages=[
            {"role": "user", "content": "Say 'Hello from OTEL v2 test!' in exactly those words."}
        ]
    )

    print(f"✅ Response: {response.choices[0].message.content}")
    print(f"📊 Tokens - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")
    print()

except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

# Force flush to send data immediately
print("🔄 Flushing traces and logs...")
tracer_provider.force_flush()
logger_provider.force_flush()
print("✅ Flush complete")
print()

# Wait a moment for data to be processed
print("⏳ Waiting 2 seconds for backend processing...")
time.sleep(2)

print("=" * 60)
print("Test complete!")
print()
print("Next steps:")
print("1. Check backend logs for 'otel_logs_received':")
print("   grep 'otel_logs' /tmp/posthog-backend.log | tail -20")
print()
print("2. Check ClickHouse for the trace with message content:")
print("   Look for trace ID in PostHog UI")
print("=" * 60)
