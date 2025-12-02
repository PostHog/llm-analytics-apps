"""
LlamaIndex provider with OpenTelemetry instrumentation.

This provider demonstrates automatic instrumentation using LlamaIndex's OTEL integration
which sends traces to PostHog's OTEL endpoint for RAG query analysis.

Requires: llama-index-core, llama-index-observability-otel, llama-index-llms-openai
"""

import os
from posthog import Posthog
from llama_index.core import VectorStoreIndex, Document
from llama_index.llms.openai import OpenAI
from llama_index.observability.otel import LlamaIndexOpenTelemetry
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

from .base import BaseProvider
from .constants import SYSTEM_PROMPT_FRIENDLY


class LlamaIndexOtelProvider(BaseProvider):
    """LlamaIndex provider with OpenTelemetry instrumentation for PostHog."""

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

        # Extract session ID from PostHog super_properties
        self.session_id = None
        if hasattr(posthog_client, 'super_properties') and posthog_client.super_properties:
            self.session_id = posthog_client.super_properties.get("$ai_session_id")

        # Setup OpenTelemetry instrumentation
        self._setup_otel()

        # Create sample documents for RAG
        self.documents = self._create_sample_documents()

        # Create LlamaIndex with OpenAI LLM
        self.llm = OpenAI(
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.7,
        )

        # Create vector index from documents
        self.index = VectorStoreIndex.from_documents(
            self.documents,
            llm=self.llm,
        )

        # Create query engine
        self.query_engine = self.index.as_query_engine(
            llm=self.llm,
            similarity_top_k=3,
        )

        # Initialize conversation context
        self.conversation_history = []

        if self.debug_mode:
            print(f"✅ LlamaIndex OTEL provider initialized")
            print(f"   📚 Loaded {len(self.documents)} documents into RAG")

    def _setup_otel(self):
        """Setup OpenTelemetry with PostHog OTLP endpoint."""
        # Check if already configured
        if hasattr(LlamaIndexOtelProvider, '_otel_configured'):
            return

        # Configure OTLP exporter for PostHog
        otlp_endpoint = f"{self.posthog_host}/api/projects/{self.posthog_project_id}/ai/otel/v1/traces"

        span_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers={"Authorization": f"Bearer {self.posthog_api_key}"},
        )

        # Create resource with service info
        resource = Resource.create({
            "service.name": "llama-index-otel-provider",
            "service.version": "1.0.0",
            "deployment.environment": "development",
        })

        # Initialize LlamaIndex OpenTelemetry instrumentation
        instrumentor = LlamaIndexOpenTelemetry(
            service_name_or_resource=resource,
            span_exporter=span_exporter,
            debug=self.debug_mode,
        )
        instrumentor.start_registering()

        # Mark as configured
        LlamaIndexOtelProvider._otel_configured = True

        if self.debug_mode:
            print(f"✅ OpenTelemetry configured to send to: {otlp_endpoint}")

    def _create_sample_documents(self):
        """Create sample documents for RAG demonstration."""
        documents = [
            Document(
                text="""
                Weather Information Database

                San Francisco: Typically mild weather year-round. Summer temperatures
                average 60-70°F (15-21°C). Famous for fog and microclimates.

                Dublin, Ireland: Temperate oceanic climate. Mild summers around 60-65°F
                (15-18°C), cool winters around 40-45°F (4-7°C). Rain is common year-round.

                Paris, France: Continental climate with warm summers around 70-75°F
                (21-24°C) and cool winters around 35-45°F (2-7°C).
                """,
                metadata={"source": "weather_db", "category": "weather"}
            ),
            Document(
                text="""
                Programming Jokes Collection

                Why do programmers prefer dark mode? Because light attracts bugs!

                Why do Java developers wear glasses? Because they can't C#!

                How many programmers does it take to change a light bulb?
                None, that's a hardware problem!

                A SQL query walks into a bar, walks up to two tables and asks: "Can I join you?"
                """,
                metadata={"source": "jokes_db", "category": "jokes"}
            ),
            Document(
                text="""
                Technology and AI Facts

                LlamaIndex is a data framework for LLM applications to ingest, structure,
                and access private or domain-specific data. It provides tools for RAG
                (Retrieval Augmented Generation).

                OpenTelemetry is an observability framework for cloud-native software,
                providing APIs and tools for collecting distributed traces and metrics.

                PostHog is a product analytics platform that helps teams understand user
                behavior and build better products.
                """,
                metadata={"source": "tech_db", "category": "technology"}
            ),
            Document(
                text="""
                General Knowledge

                The assistant is designed to be helpful, harmless, and honest. It can
                answer questions about weather, tell jokes, and discuss technology topics.

                This is a demonstration of RAG (Retrieval Augmented Generation) where
                the system retrieves relevant documents and uses them to generate responses.
                """,
                metadata={"source": "general_db", "category": "general"}
            ),
        ]
        return documents

    def get_initial_messages(self):
        """Return initial messages - not used for RAG but kept for compatibility"""
        return [{
            "role": "system",
            "content": SYSTEM_PROMPT_FRIENDLY
        }]

    def get_tool_definitions(self):
        """RAG system doesn't use explicit tools"""
        return []

    def get_name(self):
        return "LlamaIndex with OpenTelemetry (RAG)"

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Query the RAG system with OTEL tracing"""
        # Store user input in conversation history
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Build context from conversation history
        context_prompt = ""
        if len(self.conversation_history) > 1:
            context_prompt = "\n\nPrevious conversation:\n"
            for msg in self.conversation_history[:-1]:  # Exclude current message
                context_prompt += f"{msg['role']}: {msg['content']}\n"

        # Prepare query with context
        full_query = f"{context_prompt}\n\nCurrent question: {user_input}" if context_prompt else user_input

        try:
            if self.debug_mode:
                print(f"\n🔍 Querying RAG system...")
                print(f"   Query: {user_input}")

            # Query the RAG system (automatically instrumented by OTEL)
            response = self.query_engine.query(full_query)

            # Extract response text
            response_text = str(response)

            # Store assistant response in conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })

            if self.debug_mode:
                print(f"   Response length: {len(response_text)} chars")
                print(f"   Source nodes: {len(response.source_nodes)}")

            return response_text

        except Exception as e:
            error_msg = f"Error querying RAG system: {str(e)}"
            if self.debug_mode:
                print(f"❌ {error_msg}")
            return error_msg
