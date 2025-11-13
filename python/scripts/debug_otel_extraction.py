#!/usr/bin/env python3
"""
Debug script to test OpenTelemetry attribute extraction from LlamaIndex traces.

This script captures real OTel spans from LlamaIndex and tests the PostHog
extraction logic to see what model/provider/token data is being extracted.
"""

import os
import sys
import json
from typing import Any
from dotenv import load_dotenv


# Standalone extraction functions (copied from PostHog)
def has_openinference_attributes(span: dict[str, Any]) -> bool:
    """Check if span has OpenInference semantic convention attributes."""
    attributes = span.get("attributes", {})
    # Check for OpenInference-specific attributes (with or without otel. prefix)
    openinference_keys = {
        "otel.llm.system", "llm.system",
        "otel.llm.provider", "llm.provider",
        "otel.llm.model_name", "llm.model_name",
        "otel.openinference.span.kind", "openinference.span.kind",
    }
    return any(key in attributes for key in openinference_keys)


def extract_openinference_attributes(span: dict[str, Any]) -> dict[str, Any]:
    """Extract attributes from OpenInference semantic conventions."""
    attributes = span.get("attributes", {})
    result: dict[str, Any] = {}

    # Provider/system (check both prefixed and non-prefixed)
    provider = (attributes.get("otel.llm.provider") or
                attributes.get("llm.provider") or
                attributes.get("otel.llm.system") or
                attributes.get("llm.system"))
    if provider:
        result["provider"] = provider

    # Model (check both prefixed and non-prefixed)
    model = attributes.get("otel.llm.model_name") or attributes.get("llm.model_name")
    if model:
        result["model"] = model

    # Tokens (check both forms)
    prompt_tokens = (attributes.get("otel.llm.token_count.prompt") or
                     attributes.get("llm.token_count.prompt"))
    if prompt_tokens is not None:
        result["input_tokens"] = int(prompt_tokens)

    completion_tokens = (attributes.get("otel.llm.token_count.completion") or
                        attributes.get("llm.token_count.completion"))
    if completion_tokens is not None:
        result["output_tokens"] = int(completion_tokens)

    # OpenInference span kind (check both forms)
    span_kind = (attributes.get("otel.openinference.span.kind") or
                 attributes.get("openinference.span.kind"))
    if span_kind:
        result["openinference_span_kind"] = span_kind

    return result


def extract_genai_attributes(span: dict[str, Any]) -> dict[str, Any]:
    """Extract attributes from GenAI semantic conventions."""
    attributes = span.get("attributes", {})
    result: dict[str, Any] = {}

    # Provider
    provider = attributes.get("gen_ai.system")
    if provider:
        result["provider"] = provider

    # Model
    model = attributes.get("gen_ai.response.model") or attributes.get("gen_ai.request.model")
    if model:
        result["model"] = model

    # Tokens
    input_tokens = attributes.get("gen_ai.usage.input_tokens")
    if input_tokens is not None:
        result["input_tokens"] = int(input_tokens)

    output_tokens = attributes.get("gen_ai.usage.output_tokens")
    if output_tokens is not None:
        result["output_tokens"] = int(output_tokens)

    return result


def determine_event_type(span: dict[str, Any], attrs: dict[str, Any]) -> str:
    """Determine AI event type from span."""
    # Check OpenInference span kind
    openinference_kind = attrs.get("openinference_span_kind", "").upper()
    if openinference_kind == "LLM":
        return "$ai_generation"
    elif openinference_kind == "EMBEDDING":
        return "$ai_embedding"

    # Check if this is an LLM call based on presence of model/provider
    has_model = attrs.get("model") is not None
    has_provider = attrs.get("provider") is not None

    if has_model and has_provider:
        return "$ai_generation"

    # Check if span is root (no parent)
    if not span.get("parent_span_id"):
        return "$ai_trace"

    # Default to generic span
    return "$ai_span"

# Load environment variables
load_dotenv()

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource

# LlamaIndex imports
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import Context
from llama_index.llms.openai import OpenAI

# OpenInference instrumentation
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor


class DebugSpanExporter:
    """Custom exporter that captures spans for analysis."""

    def __init__(self):
        self.spans = []

    def shutdown(self):
        """Shutdown the exporter."""
        pass

    def export(self, spans):
        for span in spans:
            # Convert span to dict format similar to OTLP
            span_dict = {
                'name': span.name,
                'trace_id': format(span.context.trace_id, '032x'),
                'span_id': format(span.context.span_id, '016x'),
                'parent_span_id': format(span.parent.span_id, '016x') if span.parent else None,
                'start_time_unix_nano': span.start_time,
                'end_time_unix_nano': span.end_time,
                'attributes': dict(span.attributes) if span.attributes else {},
                'status': {
                    'code': span.status.status_code.value,
                    'message': span.status.description or ''
                }
            }
            self.spans.append(span_dict)

            # Print span info
            print(f"\n{'='*80}")
            print(f"Span: {span.name}")
            print(f"{'='*80}")

            # Show key attributes
            if span.attributes:
                print("\nRaw Attributes:")
                for key, value in span.attributes.items():
                    if 'llm' in key.lower() or 'model' in key.lower() or 'openinference' in key.lower():
                        print(f"  {key}: {value}")

            # Test extraction
            print("\n--- Testing Extraction ---")

            # Check if has OpenInference attributes
            has_oi = has_openinference_attributes(span_dict)
            print(f"Has OpenInference attributes: {has_oi}")

            # Extract OpenInference
            oi_attrs = extract_openinference_attributes(span_dict)
            print(f"OpenInference extracted: {oi_attrs}")

            # Extract GenAI
            genai_attrs = extract_genai_attributes(span_dict)
            print(f"GenAI extracted: {genai_attrs}")

            # Merge
            merged = {**genai_attrs, **oi_attrs}
            print(f"Merged attributes: {merged}")

            # Determine event type
            event_type = determine_event_type(span_dict, merged)
            print(f"Event type: {event_type}")

        return None


def setup_debug_tracing():
    """Setup OpenTelemetry with debug exporter."""
    # Create resource
    resource = Resource.create({
        "service.name": "debug-llamaindex-test",
    })

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    # Add debug exporter
    debug_exporter = DebugSpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(debug_exporter))

    # Enable OpenInference instrumentation
    LlamaIndexInstrumentor().instrument()

    return debug_exporter


def run_test():
    """Run a simple LlamaIndex agent test."""
    print("\n" + "="*80)
    print("LlamaIndex OpenInference Extraction Debug Test")
    print("="*80 + "\n")

    # Setup tracing
    debug_exporter = setup_debug_tracing()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable must be set")
        sys.exit(1)

    # Create LLM
    llm = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-3.5-turbo",
        temperature=0.0
    )

    # Create simple tool
    def multiply(a: float, b: float) -> float:
        """Multiply two numbers."""
        return a * b

    # Create agent
    agent = FunctionAgent(
        tools=[multiply],
        llm=llm,
        system_prompt="You are a helpful assistant."
    )

    # Create context
    ctx = Context(agent)

    print("Running test query: 'What is 5 times 7?'")
    print("-" * 80)

    # Run query with proper async handling
    import asyncio

    async def run_agent_query():
        return await agent.run("What is 5 times 7?", ctx=ctx)

    try:
        response = asyncio.run(run_agent_query())
        print(f"\nAgent Response: {response}")
    except Exception as e:
        print(f"Error running agent: {e}")

    # Force flush
    trace.get_tracer_provider().force_flush()

    print("\n" + "="*80)
    print(f"Total spans captured: {len(debug_exporter.spans)}")
    print("="*80)

    # Summary
    print("\nSummary of LLM spans:")
    for span in debug_exporter.spans:
        if span['attributes'].get('otel.openinference.span.kind') == 'LLM':
            attrs = extract_openinference_attributes(span)
            print(f"  - {span['name']}: model={attrs.get('model')}, provider={attrs.get('provider')}")


if __name__ == "__main__":
    run_test()
