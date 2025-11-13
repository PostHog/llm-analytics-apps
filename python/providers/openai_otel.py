"""
OpenAI Chat Provider with OpenTelemetry instrumentation.

Uses the official opentelemetry-instrumentation-openai-v2 package
to send traces to PostHog's OTel endpoint.

Based on the manual instrumentation example from:
https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai/opentelemetry-instrumentation-openai-v2/examples/manual
"""

import os

# CRITICAL: Set OpenTelemetry environment variables BEFORE any OpenTelemetry or OpenAI imports
# This must be set at module level, not in a function

# Enable message content capture for GenAI instrumentation
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

# Configure OTLP exporters via environment variables (if not already set)
if "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" not in os.environ:
    posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")
    # For logs, use the /i/v1/logs endpoint which routes through the ingestion layer
    os.environ["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = f"{posthog_host}/i/v1/logs"

from posthog import Posthog
from .base import BaseProvider
from .constants import SYSTEM_PROMPT_ASSISTANT

# OpenTelemetry imports
from opentelemetry import trace, _logs
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource

# OpenAI instrumentation
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

# OpenAI imports
from openai import OpenAI


class OpenAIOtelProvider(BaseProvider):
    """OpenAI chat provider with OpenTelemetry instrumentation."""

    def __init__(self, posthog_client: Posthog):
        # Setup OpenTelemetry BEFORE initializing parent
        self._setup_opentelemetry(posthog_client)

        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "openai_otel"}

        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

        # Create OpenAI client
        self.client = OpenAI(api_key=self.OPENAI_API_KEY)

        self.conversation_history = []
        self.system_prompt = SYSTEM_PROMPT_ASSISTANT

    def _setup_opentelemetry(self, posthog_client: Posthog):
        """Configure OpenTelemetry to send traces and logs to PostHog."""
        # Get PostHog configuration
        posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")
        posthog_project_id = os.getenv("POSTHOG_PROJECT_ID", "1")
        # Use the project API key from PostHog client (not personal API key)
        posthog_api_key = posthog_client.api_key

        # Configure OTLP endpoints
        # Traces go to custom AI endpoint for transformation
        traces_endpoint = f"{posthog_host}/api/projects/{posthog_project_id}/ai/otel/v1/traces"

        # Logs endpoint configuration
        # NOTE: For local dev, logs ingestion requires capture-logs service to be exposed
        # For now, using production endpoint pattern (will fail in local dev without proxy)
        # TODO: Add Django proxy endpoint or expose capture-logs port in docker-compose
        logs_endpoint = f"{posthog_host}/i/v1/logs"

        # Create resource with service information
        resource = Resource.create({
            "service.name": "openai-chat-cli",
            "service.version": "1.0.0",
            "deployment.environment": "development",
        })

        # Configure tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Configure OTLP trace exporter with PostHog authentication
        trace_exporter = OTLPSpanExporter(
            endpoint=traces_endpoint,
            headers={
                "Authorization": f"Bearer {posthog_api_key}",
            },
        )

        # Add span processor
        span_processor = BatchSpanProcessor(trace_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Configure logger provider for message content capture
        logger_provider = LoggerProvider(resource=resource)
        _logs.set_logger_provider(logger_provider)

        # Configure OTLP log exporter with PostHog authentication
        # Note: PostHog logs ingestion uses project API key (not personal API key)
        log_exporter = OTLPLogExporter(
            endpoint=logs_endpoint,
            headers={
                "Authorization": f"Bearer {posthog_api_key}",
            },
        )

        # Add log record processor
        log_processor = BatchLogRecordProcessor(log_exporter)
        logger_provider.add_log_record_processor(log_processor)

        # Enable OpenAI instrumentation
        OpenAIInstrumentor().instrument()

        print("✅ OpenTelemetry instrumentation enabled for OpenAI")
        print(f"   Traces endpoint: {traces_endpoint}")
        print(f"   Logs endpoint: {logs_endpoint}")
        print(f"   Message capture enabled: {os.getenv('OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT')}")

    def get_tool_definitions(self):
        """Return tool definitions for function calling."""
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
                                "description": "The latitude of the location"
                            },
                            "longitude": {
                                "type": "number",
                                "description": "The longitude of the location"
                            },
                            "location_name": {
                                "type": "string",
                                "description": "A human-readable name for the location"
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
        return "OpenAI Chat (OpenTelemetry)"

    def get_description(self):
        return "💬 Simple OpenAI chat instrumented with OpenTelemetry → PostHog"

    def reset_conversation(self):
        """Reset the conversation history."""
        self.conversation_history = []

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to OpenAI and get response."""
        if base64_image:
            return "Image input not supported for OpenAI OTel provider"

        # Build messages with system prompt
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_input})

        try:
            # Call OpenAI API (automatically instrumented)
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                tools=self.get_tool_definitions()
            )

            assistant_message = response.choices[0].message

            # Handle function calls
            if assistant_message.tool_calls:
                # Add assistant message with tool calls to history
                self.conversation_history.append({
                    "role": "user",
                    "content": user_input
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        }
                        for tool_call in assistant_message.tool_calls
                    ]
                })

                # Execute tools and collect results
                tool_messages = []
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    import json
                    function_args = json.loads(tool_call.function.arguments)

                    # Execute the function
                    if function_name == "get_weather":
                        result = self.get_weather(
                            function_args["latitude"],
                            function_args["longitude"],
                            function_args["location_name"]
                        )
                    elif function_name == "tell_joke":
                        result = self.tell_joke(
                            function_args["setup"],
                            function_args["punchline"]
                        )
                    else:
                        result = f"Unknown function: {function_name}"

                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result)
                    })

                # Add tool results to history
                self.conversation_history.extend(tool_messages)

                # Call API again with tool results
                messages_with_tools = [
                    {"role": "system", "content": self.system_prompt}
                ]
                messages_with_tools.extend(self.conversation_history)

                second_response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages_with_tools,
                    temperature=0.7
                )

                final_message = second_response.choices[0].message.content
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_message
                })

                return final_message

            else:
                # No function calls, just add to history and return
                response_text = assistant_message.content
                self.conversation_history.append({"role": "user", "content": user_input})
                self.conversation_history.append({"role": "assistant", "content": response_text})

                # Debug: Log the API call
                if self.debug_mode:
                    print("\n" + "=" * 80)
                    print(f"🔍 DEBUG - OpenAI OTel")
                    print("=" * 80)
                    print(f"User Input: {user_input}")
                    print(f"Response: {response_text}")
                    print("=" * 80 + "\n")

                return response_text

        except Exception as e:
            error_msg = f"Error in OpenAI chat: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
