"""
LangChain provider with OpenTelemetry instrumentation.
"""

import os
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from posthog import Posthog

from .base import BaseProvider
from .constants import OPENAI_CHAT_MODEL, SYSTEM_PROMPT_ASSISTANT


class LangChainOtelProvider(BaseProvider):
    """LangChain provider with OpenTelemetry instrumentation."""

    _otel_configured = False

    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self._setup_otel()

        self.langchain_messages = [
            SystemMessage(content=SYSTEM_PROMPT_ASSISTANT)
        ]

        self._setup_chain()

    def _setup_otel(self):
        if LangChainOtelProvider._otel_configured:
            return

        posthog_api_key = os.getenv("POSTHOG_API_KEY")
        posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")

        if not posthog_api_key:
            raise ValueError("POSTHOG_API_KEY must be set")

        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = f"{posthog_host}/i/v0/ai/otel"
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Bearer {posthog_api_key}"

        exporter = OTLPSpanExporter()
        resource_attributes = {
            "service.name": "llm-analytics-app-langchain-otel",
            "user.id": os.getenv("POSTHOG_DISTINCT_ID", "unknown"),
        }
        if self.debug_mode:
            resource_attributes["posthog.ai.debug"] = "true"

        tracer_provider = TracerProvider(resource=Resource.create(resource_attributes))
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(tracer_provider)
        LangchainInstrumentor().instrument()

        LangChainOtelProvider._otel_configured = True

    def _setup_chain(self):
        @tool
        def get_weather(latitude: float, longitude: float, location_name: str) -> str:
            """Get the current weather for a specific location using geographical coordinates.

            Args:
                latitude: The latitude of the location (e.g., 37.7749 for San Francisco)
                longitude: The longitude of the location (e.g., -122.4194 for San Francisco)
                location_name: A human-readable name for the location (e.g., 'San Francisco, CA' or 'Dublin, Ireland')

            Returns:
                Weather information for the specified location
            """
            return self.get_weather(latitude, longitude, location_name)

        @tool
        def tell_joke(setup: str, punchline: str) -> str:
            """Tell a joke with a question-style setup and an answer punchline.

            Args:
                setup: The setup or question part of the joke
                punchline: The punchline or answer part of the joke

            Returns:
                The formatted joke
            """
            return self.tell_joke(setup, punchline)

        self.langchain_tools = [get_weather, tell_joke]
        self.tool_map = {t.name: t for t in self.langchain_tools}

    def get_name(self):
        return "LangChain with OpenTelemetry"

    def get_tool_definitions(self):
        return []

    def get_initial_messages(self) -> List[Dict[str, Any]]:
        return []

    def reset_conversation(self):
        self.langchain_messages = [
            SystemMessage(content=SYSTEM_PROMPT_ASSISTANT)
        ]
        self.messages = []

    def chat(self, user_input: str, base64_image: Optional[str] = None) -> str:
        if base64_image:
            user_message = HumanMessage(content=[
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
            ])
        else:
            user_message = HumanMessage(content=user_input)
        self.langchain_messages.append(user_message)

        model = ChatOpenAI(temperature=0, model_name=OPENAI_CHAT_MODEL)
        model_with_tools = model.bind_tools(self.langchain_tools)

        response = model_with_tools.invoke(self.langchain_messages)

        display_parts = []

        if response.content:
            display_parts.append(response.content)

        if response.tool_calls:
            tool_messages = []
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                if tool_name in self.tool_map:
                    tool_result = self.tool_map[tool_name].invoke(tool_args)
                    tool_result_text = self.format_tool_result(tool_name, tool_result)
                    display_parts.append(tool_result_text)

                    tool_messages.append(
                        ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call["id"],
                        )
                    )

        self.langchain_messages.append(response)

        if response.tool_calls:
            self.langchain_messages.extend(tool_messages)

        return "\n\n".join(display_parts) if display_parts else "No response received"
