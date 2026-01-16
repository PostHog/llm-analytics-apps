"""
OpenAI provider with OpenTelemetry v2 instrumentation.

This provider uses the official OpenAI v2 instrumentation which sends:
- Span metadata (model, tokens, etc.) to traces endpoint
- Message content (prompts/completions) as log events to logs endpoint

Requires: opentelemetry-instrumentation-openai-v2
"""

import os
import json
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
from posthog import Posthog

from .base import BaseProvider
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    DEFAULT_MAX_TOKENS,
    SYSTEM_PROMPT_FRIENDLY
)


class OpenAIOtelV2Provider(BaseProvider):
    """OpenAI provider with OpenTelemetry v2 instrumentation for PostHog."""

    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Get PostHog configuration
        self.posthog_project_id = os.getenv("POSTHOG_PROJECT_ID")
        self.posthog_api_key = os.getenv("POSTHOG_API_KEY")
        self.posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8000")

        if not self.posthog_project_id or not self.posthog_api_key:
            raise ValueError(
                "POSTHOG_PROJECT_ID and POSTHOG_API_KEY must be set in environment"
            )

        # Setup OpenTelemetry v2 (traces + logs)
        self._setup_otel_v2()

        # Create OpenAI client (will be instrumented by OTEL v2)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Initialize conversation
        self.messages = self.get_initial_messages()

    def _setup_otel_v2(self):
        """Setup OpenTelemetry v2 with PostHog OTLP endpoints for traces and logs."""
        # Check if already configured
        if hasattr(OpenAIOtelV2Provider, '_otel_configured'):
            return

        # Create resource with service name
        resource = Resource.create({
            "service.name": "llm-analytics-app-otel-v2",
            "service.version": "1.0.0",
            "deployment.environment": "development",
        })

        # Configure traces exporter
        traces_endpoint = f"{self.posthog_host}/api/projects/{self.posthog_project_id}/ai/otel/v1/traces"
        tracer_provider = TracerProvider(resource=resource)
        trace_exporter = OTLPSpanExporter(
            endpoint=traces_endpoint,
            headers={"Authorization": f"Bearer {self.posthog_api_key}"},
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        trace.set_tracer_provider(tracer_provider)

        # Configure logs exporter (v2 sends message content here)
        logs_endpoint = f"{self.posthog_host}/api/projects/{self.posthog_project_id}/ai/otel/v1/logs"
        logger_provider = LoggerProvider(resource=resource)
        log_exporter = OTLPLogExporter(
            endpoint=logs_endpoint,
            headers={"Authorization": f"Bearer {self.posthog_api_key}"},
        )
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        _logs.set_logger_provider(logger_provider)

        # Configure event logger provider (v2 uses Events API which wraps Logs API)
        event_logger_provider = EventLoggerProvider(logger_provider=logger_provider)
        _events.set_event_logger_provider(event_logger_provider)

        # Enable message content capture (v2 requires explicit opt-in)
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

        # Instrument OpenAI SDK with v2 instrumentation
        OpenAIInstrumentor().instrument()

        # Mark as configured
        OpenAIOtelV2Provider._otel_configured = True

        if self.debug_mode:
            print(f"✅ OpenTelemetry v2 configured:")
            print(f"   Traces → {traces_endpoint}")
            print(f"   Logs   → {logs_endpoint}")

    def get_initial_messages(self):
        """Return initial messages with system prompt"""
        return [{
            "role": "system",
            "content": SYSTEM_PROMPT_FRIENDLY
        }]

    def get_tool_definitions(self):
        """Return tool definitions in OpenAI Chat format"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a specific location using geographical coordinates",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {
                                "type": "number",
                                "description": "The latitude of the location (e.g., 37.7749 for San Francisco)"
                            },
                            "longitude": {
                                "type": "number",
                                "description": "The longitude of the location (e.g., -122.4194 for San Francisco)"
                            },
                            "location_name": {
                                "type": "string",
                                "description": "A human-readable name for the location (e.g., 'San Francisco, CA' or 'Dublin, Ireland')"
                            }
                        },
                        "required": ["latitude", "longitude", "location_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "tell_joke",
                    "description": "Tell a joke with a question-style setup and an answer punchline",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "setup": {
                                "type": "string",
                                "description": "The setup or question part of the joke"
                            },
                            "punchline": {
                                "type": "string",
                                "description": "The punchline or answer part of the joke"
                            }
                        },
                        "required": ["setup", "punchline"]
                    }
                }
            }
        ]

    def get_name(self):
        return "OpenAI with OpenTelemetry v2"

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to OpenAI and get response with OTEL v2 tracing"""
        # Add user message to history
        if base64_image:
            user_content = [
                {
                    "type": "text",
                    "text": user_input
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        else:
            user_content = user_input

        user_message = {
            "role": "user",
            "content": user_content
        }
        self.messages.append(user_message)

        # Use vision model for images
        model_name = OPENAI_VISION_MODEL if base64_image else OPENAI_CHAT_MODEL

        # Prepare API request parameters
        request_params = {
            "model": model_name,
            "max_completion_tokens": DEFAULT_MAX_TOKENS,
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": "auto",
        }

        # Call OpenAI (automatically instrumented by OTEL v2)
        # Message content is sent as log events to logs endpoint
        response = self.client.chat.completions.create(**request_params)

        # Force flush logs to ensure they're sent immediately (for debugging)
        from opentelemetry import _logs
        logger_provider = _logs.get_logger_provider()
        if hasattr(logger_provider, 'force_flush'):
            logger_provider.force_flush()

        # Debug: Log the API call
        self._debug_api_call("OpenAI OTEL v2", request_params, response)

        # Collect response parts for display
        display_parts = []
        assistant_content = ""

        # Extract response
        choice = response.choices[0]
        message = choice.message

        # Handle text content
        if message.content:
            assistant_content = message.content
            display_parts.append(message.content)

        # Handle tool calls
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "get_weather":
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        latitude = arguments.get("latitude", 0.0)
                        longitude = arguments.get("longitude", 0.0)
                        location_name = arguments.get("location_name")
                        weather_result = self.get_weather(latitude, longitude, location_name)
                        tool_result_text = self.format_tool_result("get_weather", weather_result)
                        display_parts.append(tool_result_text)

                        # Add tool response to conversation history
                        self.messages.append({
                            "role": "assistant",
                            "content": assistant_content,
                            "tool_calls": [{
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments
                                }
                            }]
                        })

                        # Add tool result message
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": weather_result
                        })

                    except json.JSONDecodeError:
                        display_parts.append("❌ Error parsing tool arguments")

                elif tool_call.function.name == "tell_joke":
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        setup = arguments.get("setup", "")
                        punchline = arguments.get("punchline", "")
                        joke_result = self.tell_joke(setup, punchline)
                        tool_result_text = self.format_tool_result("tell_joke", joke_result)
                        display_parts.append(tool_result_text)

                        # Add tool response to conversation history
                        self.messages.append({
                            "role": "assistant",
                            "content": assistant_content,
                            "tool_calls": [{
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments
                                }
                            }]
                        })

                        # Add tool result message
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": joke_result
                        })

                    except json.JSONDecodeError:
                        display_parts.append("❌ Error parsing tool arguments")
        else:
            # Add assistant's response to conversation history (text only)
            if assistant_content:
                assistant_message = {
                    "role": "assistant",
                    "content": assistant_content
                }
                self.messages.append(assistant_message)

        return "\n\n".join(display_parts) if display_parts else "No response received"
