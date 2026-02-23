"""
Pydantic AI provider with OpenTelemetry instrumentation.
"""

import os
from typing import List, Dict, Any, Optional
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from posthog import Posthog

from .base import BaseProvider
from .constants import OPENAI_CHAT_MODEL, SYSTEM_PROMPT_FRIENDLY


class PydanticAIOtelProvider(BaseProvider):
    """Pydantic AI provider with OpenTelemetry instrumentation."""

    _otel_configured = False

    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self._setup_otel()
        self.model = OpenAIModel(OPENAI_CHAT_MODEL)
        self.agent = self._create_agent()

    def _setup_otel(self):
        if PydanticAIOtelProvider._otel_configured:
            return

        posthog_api_key = os.getenv("POSTHOG_API_KEY")
        posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")

        if not posthog_api_key:
            raise ValueError("POSTHOG_API_KEY must be set")

        # Configure OTLP exporter via env vars (following Pydantic AI docs pattern)
        # Use TRACES_ENDPOINT to avoid automatic /v1/traces suffix
        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = f"{posthog_host}/i/v0/llma_otel"
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Bearer {posthog_api_key}"

        exporter = OTLPSpanExporter()
        resource_attributes = {
            "service.name": "llm-analytics-app-pydantic-ai",
            "user.id": os.getenv("POSTHOG_DISTINCT_ID", "unknown"),
        }
        if self.debug_mode:
            resource_attributes["posthog.ai.debug"] = "true"

        tracer_provider = TracerProvider(resource=Resource.create(resource_attributes))
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(tracer_provider)
        Agent.instrument_all()
        # End of OTEL setup

        PydanticAIOtelProvider._otel_configured = True

    def _create_agent(self) -> Agent:
        agent = Agent(self.model, system_prompt=SYSTEM_PROMPT_FRIENDLY)

        @agent.tool
        def get_weather(ctx: RunContext[None], latitude: float, longitude: float, location_name: str) -> str:
            """Get current weather for a location."""
            return BaseProvider.get_weather(self, latitude, longitude, location_name)

        @agent.tool
        def tell_joke(ctx: RunContext[None], setup: str, punchline: str) -> str:
            """Tell a joke."""
            return BaseProvider.tell_joke(self, setup, punchline)

        return agent

    def get_name(self) -> str:
        return "Pydantic AI with OpenTelemetry"

    def get_initial_messages(self) -> List[Dict[str, Any]]:
        return []

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return []

    def chat(self, user_input: str, base64_image: Optional[str] = None) -> str:
        result = self.agent.run_sync(user_input)
        return result.output
