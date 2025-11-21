#!/usr/bin/env python
"""
Test: OTEL v1 - Multi-turn conversation with tools
"""
import os
import json
from openai import OpenAI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

API_KEY = os.getenv("OPENAI_API_KEY")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "phc_test")
POSTHOG_PROJECT_ID = os.getenv("POSTHOG_PROJECT_ID", "1")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8000")

print("\n" + "=" * 80)
print("TEST: OTEL v1 - Multi-turn Conversation with Tools")
print("=" * 80)

if not API_KEY:
    print("❌ OPENAI_API_KEY not set")
    exit(1)

# Setup OTEL v1
resource = Resource.create({
    "service.name": "otel-v1-conversation",
    "user.id": "v1-conversation-test"
})

traces_endpoint = f"{POSTHOG_HOST}/api/projects/{POSTHOG_PROJECT_ID}/ai/otel/v1/traces"
tracer_provider = TracerProvider(resource=resource)
trace_exporter = OTLPSpanExporter(
    endpoint=traces_endpoint,
    headers={"Authorization": f"Bearer {POSTHOG_API_KEY}"},
)
tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
trace.set_tracer_provider(tracer_provider)

os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
OpenAIInstrumentor().instrument()

client = OpenAI(api_key=API_KEY)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tell_joke",
            "description": "Tell a joke",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Joke topic"}
                }
            }
        }
    }
]

messages = [
    {"role": "system", "content": "You are a helpful assistant with access to weather and jokes."}
]

print("\n🗣️  CONVERSATION:")
print("-" * 80)

try:
    # Turn 1: Greeting
    print("\n[1] User: Hi there!")
    messages.append({"role": "user", "content": "Hi there!"})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        max_tokens=100
    )

    msg = response.choices[0].message.content
    messages.append({"role": "assistant", "content": msg})
    print(f"[1] Assistant: {msg}")

    # Turn 2: Weather tool call
    print("\n[2] User: What's the weather in Paris?")
    messages.append({"role": "user", "content": "What's the weather in Paris?"})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        max_tokens=100
    )

    choice = response.choices[0]
    if choice.message.tool_calls:
        tool_call = choice.message.tool_calls[0]
        print(f"[2] Assistant: [Calling {tool_call.function.name}]")

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            }]
        })

        weather_result = "Sunny, 18°C"
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": weather_result
        })

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            max_tokens=100
        )

        msg = response.choices[0].message.content
        messages.append({"role": "assistant", "content": msg})
        print(f"[2] Assistant: {msg}")

    # Turn 3: Joke tool call
    print("\n[3] User: Tell me a joke about coding")
    messages.append({"role": "user", "content": "Tell me a joke about coding"})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        max_tokens=100
    )

    choice = response.choices[0]
    if choice.message.tool_calls:
        tool_call = choice.message.tool_calls[0]
        print(f"[3] Assistant: [Calling {tool_call.function.name}]")

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            }]
        })

        joke = "Why do programmers prefer dark mode? Because light attracts bugs!"
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": joke
        })

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            max_tokens=100
        )

        msg = response.choices[0].message.content
        messages.append({"role": "assistant", "content": msg})
        print(f"[3] Assistant: {msg}")

    # Turn 4: Goodbye
    print("\n[4] User: Thanks, bye!")
    messages.append({"role": "user", "content": "Thanks, bye!"})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        max_tokens=100
    )

    msg = response.choices[0].message.content
    messages.append({"role": "assistant", "content": msg})
    print(f"[4] Assistant: {msg}")

    print("\n" + "-" * 80)
    print(f"✅ Conversation complete! Total messages: {len(messages)}")
    print("   Method: OTEL v1 (everything in span attributes)")
    print("   Distinct ID: v1-conversation-test")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

tracer_provider.force_flush()
print("\n" + "=" * 80)
