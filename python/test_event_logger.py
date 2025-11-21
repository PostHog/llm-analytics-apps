"""
Debug script to check if EventLogger is working correctly.
"""

import os
from opentelemetry import _logs
from opentelemetry._events import get_event_logger
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import ConsoleLogExporter, BatchLogRecordProcessor

# Setup logger provider with console exporter for debugging
logger_provider = LoggerProvider()
console_exporter = ConsoleLogExporter()
logger_provider.add_log_record_processor(BatchLogRecordProcessor(console_exporter))
_logs.set_logger_provider(logger_provider)

# Get event logger (this is what v2 instrumentation uses)
event_logger = get_event_logger("test")

print("=" * 60)
print("Testing EventLogger")
print("=" * 60)

# Emit a test event
from opentelemetry._logs import LogRecord

test_event = LogRecord(
    event_name="test.event",
    attributes={"test.attribute": "test_value"},
    body={"content": "This is a test message"}
)

print("Emitting test event...")
event_logger.emit(test_event)

print("Forcing flush...")
logger_provider.force_flush()

print("Done!")
print("=" * 60)
print()
print("If you see log output above, EventLogger is working.")
print("If not, there's an issue with the EventLogger setup.")
