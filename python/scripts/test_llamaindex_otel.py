#!/usr/bin/env python3
"""
Test script for LlamaIndex with OpenTelemetry instrumentation sending to PostHog.

This script demonstrates:
- LlamaIndex with OpenTelemetry observability
- OTLP exporter configured to send traces to PostHog's OTel endpoint
- Simple RAG pipeline with trace collection

Usage:
    python test_llamaindex_otel.py                    # Run with default settings
    python test_llamaindex_otel.py --debug            # Enable debug logging
    python test_llamaindex_otel.py --queries 5        # Run 5 queries

Prerequisites:
    - OPENAI_API_KEY must be set in .env
    - Local PostHog instance running at http://localhost:8010
    - Or set POSTHOG_HOST and POSTHOG_API_KEY for remote PostHog
"""

import os
import sys
import argparse
import time
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
load_dotenv()

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# LlamaIndex imports
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.events import BaseEvent
from llama_index.core.instrumentation.event_handlers import BaseEventHandler
from llama_index.core.instrumentation.span_handlers import SimpleSpanHandler
from llama_index.llms.openai import OpenAI


def setup_opentelemetry():
    """
    Configure OpenTelemetry to send traces to PostHog's OTLP endpoint.

    Returns:
        tuple: (tracer, project_id, api_token) for verification
    """
    # Get PostHog configuration
    posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")
    posthog_api_key = os.getenv("POSTHOG_API_KEY")
    posthog_project_id = os.getenv("POSTHOG_PROJECT_ID", "1")  # Default to project 1 for local dev

    if not posthog_api_key:
        print("❌ Error: POSTHOG_API_KEY environment variable must be set")
        print("   For local dev, get your API key with: python scripts/get_localhost_api_key.py")
        sys.exit(1)

    # Configure OTLP endpoint for PostHog
    otlp_endpoint = f"{posthog_host}/api/projects/{posthog_project_id}/ai/otel/v1/traces"

    print("\n" + "="*80)
    print("🔧 OpenTelemetry Configuration")
    print("="*80)
    print(f"  PostHog Host:     {posthog_host}")
    print(f"  Project ID:       {posthog_project_id}")
    print(f"  OTLP Endpoint:    {otlp_endpoint}")
    print(f"  API Key:          {posthog_api_key[:10]}..." if len(posthog_api_key) > 10 else f"  API Key:          {posthog_api_key}")
    print()

    # Create resource with service information
    resource = Resource.create({
        "service.name": "llamaindex-otel-test",
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

    # Get tracer
    tracer = trace.get_tracer(__name__)

    print("✅ OpenTelemetry configured successfully!")
    print()

    return tracer, posthog_project_id, posthog_api_key


class LlamaIndexEventHandler(BaseEventHandler):
    """Custom event handler to log LlamaIndex events."""

    @classmethod
    def class_name(cls) -> str:
        return "LlamaIndexEventHandler"

    def handle(self, event: BaseEvent) -> None:
        """Handle events from LlamaIndex."""
        print(f"  📊 Event: {event.__class__.__name__}")


def create_sample_documents():
    """
    Create sample documents for testing.

    Returns:
        list: List of sample documents
    """
    from llama_index.core import Document

    documents = [
        Document(
            text="""
            PostHog is an open-source product analytics platform that helps you
            understand user behavior. It provides features like event tracking,
            session recording, feature flags, and A/B testing.
            """,
            metadata={"source": "posthog_info", "category": "product"}
        ),
        Document(
            text="""
            OpenTelemetry is an observability framework for cloud-native software.
            It provides a single set of APIs, libraries, agents, and instrumentation
            to capture distributed traces and metrics from your application.
            """,
            metadata={"source": "otel_info", "category": "observability"}
        ),
        Document(
            text="""
            LlamaIndex is a data framework for LLM applications. It helps you
            ingest, structure, and access private or domain-specific data for
            use with large language models.
            """,
            metadata={"source": "llamaindex_info", "category": "ai_framework"}
        ),
    ]

    return documents


def run_llamaindex_queries(tracer, num_queries=3, debug=False):
    """
    Run LlamaIndex queries with OpenTelemetry tracing.

    Args:
        tracer: OpenTelemetry tracer instance
        num_queries: Number of queries to run
        debug: Enable debug logging
    """
    print("\n" + "="*80)
    print("🦙 Setting up LlamaIndex with OpenTelemetry")
    print("="*80 + "\n")

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable must be set")
        sys.exit(1)

    # Enable OpenInference instrumentation for LlamaIndex
    # This automatically creates spans for all LlamaIndex operations
    from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

    print("🔌 Instrumenting LlamaIndex with OpenTelemetry...")
    LlamaIndexInstrumentor().instrument()
    print("✅ LlamaIndex instrumentation enabled!\n")

    # Configure LlamaIndex
    Settings.llm = OpenAI(model="gpt-3.5-turbo", temperature=0.1)

    # Add event handler for logging (optional)
    if debug:
        dispatcher = get_dispatcher()
        event_handler = LlamaIndexEventHandler()
        dispatcher.add_event_handler(event_handler)

    print("📚 Creating sample document index...")

    # Create sample documents
    documents = create_sample_documents()

    # Create index
    with tracer.start_as_current_span("create_index") as span:
        span.set_attribute("document_count", len(documents))
        index = VectorStoreIndex.from_documents(documents)

    print(f"✅ Index created with {len(documents)} documents\n")

    # Create query engine
    query_engine = index.as_query_engine()

    # Sample queries
    queries = [
        "What is PostHog?",
        "Tell me about OpenTelemetry",
        "How does LlamaIndex help with LLM applications?",
        "What observability tools are mentioned?",
        "Compare PostHog and OpenTelemetry",
    ]

    print("="*80)
    print(f"🔍 Running {num_queries} Queries with Tracing")
    print("="*80 + "\n")

    # Run queries
    for i in range(min(num_queries, len(queries))):
        query = queries[i]

        print(f"Query {i+1}: {query}")
        print("-" * 80)

        try:
            # Execute query with tracing
            with tracer.start_as_current_span(f"query_{i+1}") as span:
                span.set_attribute("query_text", query)
                span.set_attribute("query_number", i + 1)

                response = query_engine.query(query)

                span.set_attribute("response_length", len(str(response)))

                print(f"Response: {response}\n")

                if debug:
                    print(f"  📝 Source nodes: {len(response.source_nodes)}")
                    for j, node in enumerate(response.source_nodes):
                        print(f"     {j+1}. Score: {node.score:.4f} - Source: {node.metadata.get('source', 'unknown')}")
                    print()

        except Exception as e:
            print(f"❌ Error processing query: {str(e)}\n")
            import traceback
            traceback.print_exc()

        # Small delay between queries
        if i < num_queries - 1:
            time.sleep(0.5)

    print("="*80)
    print("✅ All queries completed!")
    print("="*80 + "\n")


def verify_traces_sent(project_id, api_key):
    """
    Verify that traces were sent to PostHog.

    Args:
        project_id: PostHog project ID
        api_key: PostHog API key
    """
    print("\n" + "="*80)
    print("🔍 Verifying Traces in PostHog")
    print("="*80 + "\n")

    posthog_host = os.getenv("POSTHOG_HOST", "http://localhost:8010")

    print(f"Check traces in PostHog:")
    print(f"  🌐 Open: {posthog_host}")
    print(f"  📊 Navigate to: LLM Analytics / AI Traces")
    print(f"  🔎 Filter by: service.name = 'llamaindex-otel-test'")
    print()
    print("Expected trace structure:")
    print("  • create_index span")
    print("  • query_1, query_2, query_3 spans")
    print("  • LlamaIndex internal spans (embedding, retrieval, LLM calls)")
    print()


def main():
    """Run LlamaIndex with OpenTelemetry test."""
    parser = argparse.ArgumentParser(
        description="Test LlamaIndex with OpenTelemetry tracing to PostHog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_llamaindex_otel.py                    # Run with defaults
  python test_llamaindex_otel.py --queries 5        # Run 5 queries
  python test_llamaindex_otel.py --debug            # Enable debug logging

Environment Variables:
  POSTHOG_HOST         - PostHog instance URL (default: http://localhost:8010)
  POSTHOG_API_KEY      - PostHog project API key (required)
  POSTHOG_PROJECT_ID   - PostHog project ID (default: 1)
  OPENAI_API_KEY       - OpenAI API key (required)
        """
    )

    parser.add_argument(
        '--queries', '-q',
        type=int,
        default=3,
        help='Number of queries to run (default: 3, max: 5)'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    print("\n" + "="*80)
    print("🚀 LlamaIndex + OpenTelemetry → PostHog Test")
    print("="*80)

    try:
        # Setup OpenTelemetry
        tracer, project_id, api_key = setup_opentelemetry()

        # Run LlamaIndex queries
        run_llamaindex_queries(tracer, num_queries=args.queries, debug=args.debug)

        # Force flush spans before exit
        print("📤 Flushing traces to PostHog...")
        trace.get_tracer_provider().force_flush()
        time.sleep(2)  # Give time for async export
        print("✅ Traces flushed!\n")

        # Verify
        verify_traces_sent(project_id, api_key)

        print("\n" + "="*80)
        print("✅ Test completed successfully!")
        print("="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
