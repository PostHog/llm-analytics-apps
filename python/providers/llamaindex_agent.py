"""
LlamaIndex Agent Provider with OpenTelemetry instrumentation.

Uses LlamaIndex ReAct agent with tools, instrumented via OpenInference
to send traces to PostHog's OTel endpoint.
"""

import os
from posthog import Posthog
from .base import BaseProvider
from .constants import SYSTEM_PROMPT_ASSISTANT

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# OpenInference instrumentation for LlamaIndex
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

# LlamaIndex imports
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import Context
from llama_index.llms.openai import OpenAI
import asyncio


class LlamaIndexAgentProvider(BaseProvider):
    """LlamaIndex agent provider with OpenTelemetry instrumentation."""

    def __init__(self, posthog_client: Posthog):
        # Setup OpenTelemetry BEFORE initializing parent (which calls get_tool_definitions)
        self._setup_opentelemetry(posthog_client)

        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "llamaindex_agent"}

        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

        # Create LLM
        self.llm = OpenAI(
            api_key=self.OPENAI_API_KEY,
            model="gpt-3.5-turbo",
            temperature=0.0
        )

        # Create tools (as plain functions, not FunctionTool objects)
        self.tools = self._create_tools()

        # Create FunctionAgent
        self.agent = FunctionAgent(
            tools=self.tools,
            llm=self.llm,
            system_prompt="You are a helpful assistant with access to weather data, jokes, and math tools."
        )

        # Create context for chat history
        self.context = Context(self.agent)

        self.conversation_history = []

    def _setup_opentelemetry(self, posthog_client: Posthog):
        """Configure OpenTelemetry to send traces to PostHog."""
        # Get PostHog configuration
        posthog_host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
        posthog_project_id = os.getenv("POSTHOG_PROJECT_ID", "1")
        posthog_api_key = os.getenv("POSTHOG_API_KEY")

        # Configure OTLP endpoint
        otlp_endpoint = f"{posthog_host}/api/projects/{posthog_project_id}/ai/otel/v1/traces"

        # Create resource with service information
        resource = Resource.create({
            "service.name": "llamaindex-agent-cli",
            "service.version": "1.0.0",
            "deployment.environment": "development",
        })

        # Configure tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Configure OTLP exporter with PostHog authentication
        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers={
                "Authorization": f"Bearer {posthog_api_key}",
            },
        )

        # Add span processor
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Enable OpenInference instrumentation for LlamaIndex
        LlamaIndexInstrumentor().instrument()

        print("✅ OpenTelemetry instrumentation enabled for LlamaIndex")
        print(f"   Endpoint: {otlp_endpoint}")

    def _create_tools(self):
        """Create tool functions for the agent."""

        def get_weather_tool(latitude: float, longitude: float, location_name: str) -> str:
            """Get the current weather for a specific location using geographical coordinates.

            Args:
                latitude: The latitude of the location (e.g., 37.7749 for San Francisco)
                longitude: The longitude of the location (e.g., -122.4194 for San Francisco)
                location_name: A human-readable name for the location (e.g., 'San Francisco, CA')

            Returns:
                Weather information for the specified location
            """
            return self.get_weather(latitude, longitude, location_name)

        def tell_joke_tool(setup: str, punchline: str) -> str:
            """Tell a joke with a question-style setup and an answer punchline.

            Args:
                setup: The setup or question part of the joke
                punchline: The punchline or answer part of the joke

            Returns:
                The formatted joke
            """
            return self.tell_joke(setup, punchline)

        def multiply(a: float, b: float) -> float:
            """Multiply two numbers and return the result.

            Args:
                a: First number
                b: Second number

            Returns:
                The product of a and b
            """
            return a * b

        def add(a: float, b: float) -> float:
            """Add two numbers and return the result.

            Args:
                a: First number
                b: Second number

            Returns:
                The sum of a and b
            """
            return a + b

        # Return plain functions (not FunctionTool objects)
        return [get_weather_tool, tell_joke_tool, multiply, add]

    def get_tool_definitions(self):
        """Return tool definitions (not used by LlamaIndex but required by base)."""
        return []

    def get_name(self):
        return "LlamaIndex Agent (OpenTelemetry)"

    def get_description(self):
        return "🤖 ReAct agent with weather, jokes, and math tools! Instrumented with OpenTelemetry → PostHog"

    def reset_conversation(self):
        """Reset the conversation history."""
        self.conversation_history = []
        # Recreate agent and context to reset chat history
        self.agent = FunctionAgent(
            tools=self.tools,
            llm=self.llm,
            system_prompt="You are a helpful assistant with access to weather data, jokes, and math tools."
        )
        self.context = Context(self.agent)

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to the LlamaIndex agent and get response."""
        if base64_image:
            return "Image input not supported for LlamaIndex agent"

        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})

        try:
            # Create async wrapper to properly handle the agent run
            async def run_agent():
                return await self.agent.run(user_input, ctx=self.context)

            # Get agent response using async run method with context for chat history
            response = asyncio.run(run_agent())

            # Extract response text
            response_text = str(response)

            # Add to conversation history
            self.conversation_history.append({"role": "assistant", "content": response_text})

            # Debug: Log the API call
            if self.debug_mode:
                print("\n" + "=" * 80)
                print(f"🔍 DEBUG - LlamaIndex Agent")
                print("=" * 80)
                print(f"User Input: {user_input}")
                print(f"Agent Response: {response_text}")
                print("=" * 80 + "\n")

            return response_text

        except Exception as e:
            error_msg = f"Error in agent chat: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
