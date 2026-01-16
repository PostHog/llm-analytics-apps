#!/usr/bin/env python
"""
Test: PostHog Python SDK - Multi-turn conversation with tools
"""
import os
import json
from posthog import Posthog
from posthog.ai.openai import OpenAI

API_KEY = os.getenv("OPENAI_API_KEY")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "phc_test")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "http://localhost:8000")

print("\n" + "=" * 80)
print("TEST: PostHog SDK - Multi-turn Conversation with Tools")
print("=" * 80)

if not API_KEY:
    print("❌ OPENAI_API_KEY not set")
    exit(1)

# Initialize PostHog
posthog = Posthog(
    project_api_key=POSTHOG_API_KEY,
    host=POSTHOG_HOST,
    sync_mode=True
)

client = OpenAI(api_key=API_KEY, posthog_client=posthog)

# Tool definitions
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
        posthog_distinct_id="sdk-conversation-test",
        posthog_properties={
            "$ai_span_name": "chat.greeting",
            "test_environment": "posthog-sdk-test",
            "test_value": "turn-1-greeting"
        },
        max_tokens=100
    )

    msg = response.choices[0].message.content
    messages.append({"role": "assistant", "content": msg})
    print(f"[1] Assistant: {msg}")

    # Turn 2: Ask for weather (triggers tool)
    print("\n[2] User: What's the weather in Paris?")
    messages.append({"role": "user", "content": "What's the weather in Paris?"})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        posthog_distinct_id="sdk-conversation-test",
        posthog_properties={
            "$ai_span_name": "chat.tool_call",
            "test_environment": "posthog-sdk-test",
            "test_value": "turn-2-weather-request"
        },
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

        # Simulate tool response
        weather_result = "Sunny, 18°C"
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": weather_result
        })

        # Get final response with tool result
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            posthog_distinct_id="sdk-conversation-test",
            posthog_properties={
                "$ai_span_name": "chat.tool_response",
                "test_environment": "posthog-sdk-test",
                "test_value": "turn-2-weather-response"
            },
            max_tokens=100
        )

        msg = response.choices[0].message.content
        messages.append({"role": "assistant", "content": msg})
        print(f"[2] Assistant: {msg}")

    # Turn 3: Ask for a joke
    print("\n[3] User: Tell me a joke about coding")
    messages.append({"role": "user", "content": "Tell me a joke about coding"})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        posthog_distinct_id="sdk-conversation-test",
        posthog_properties={
            "$ai_span_name": "chat.tool_call",
            "test_environment": "posthog-sdk-test",
            "test_value": "turn-3-joke-request"
        },
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

        # Simulate joke
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
            posthog_distinct_id="sdk-conversation-test",
            posthog_properties={
                "$ai_span_name": "chat.tool_response",
                "test_environment": "posthog-sdk-test",
                "test_value": "turn-3-joke-response"
            },
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
        posthog_distinct_id="sdk-conversation-test",
        posthog_properties={
            "$ai_span_name": "chat.farewell",
            "test_environment": "posthog-sdk-test",
            "test_value": "turn-4-goodbye"
        },
        max_tokens=100
    )

    msg = response.choices[0].message.content
    messages.append({"role": "assistant", "content": msg})
    print(f"[4] Assistant: {msg}")

    print("\n" + "-" * 80)
    print(f"✅ Conversation complete! Total messages: {len(messages)}")
    print("   Method: PostHog SDK")
    print("   Distinct ID: sdk-conversation-test")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

posthog.shutdown()
print("\n" + "=" * 80)
