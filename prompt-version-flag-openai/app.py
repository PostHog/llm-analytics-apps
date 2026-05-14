import json
import os
import random
import uuid
from pathlib import Path

from dotenv import load_dotenv
from posthog import Posthog
from posthog.ai.prompts import Prompts

load_dotenv(Path(__file__).with_name(".env"))


def show(title, value):
    print(f"\n--- {title} ---")
    print(value)


def env(name, default=None):
    value = os.getenv(name, default)
    if value in (None, ""):
        raise RuntimeError(f"Missing {name}")
    return value


posthog = Posthog(
    env("POSTHOG_API_KEY"),
    host=env("POSTHOG_HOST"),
    personal_api_key=env("POSTHOG_PERSONAL_API_KEY"),
    feature_flags_request_timeout_seconds=3,
)

flag_key = env("POSTHOG_PROMPT_CONFIG_FLAG_KEY")
max_iterations = int(env("MAX_ITERATIONS", "10"))
prompts = Prompts(posthog)

user_message = "Tell me a fun fact about hedgehogs"
mock_response = "Hedgehogs have around 5,000 to 7,000 spines on their backs!"

for iteration in range(1, max_iterations + 1):
    show(f"Iteration {iteration}/{max_iterations}", "")

    distinct_id = str(uuid.uuid4()) + "_toto"
    trace_id = str(uuid.uuid4()) + "_toto"
    show("Distinct ID", distinct_id)

    flags = posthog.evaluate_flags(distinct_id, flag_keys=[flag_key])
    # flag_value = flags.get_flag(flag_key)
    payload = flags.get_flag_payload(flag_key) or {}

    # posthog.get_feature_flag(flag_key, distinct_id)
    # payload = posthog.get_feature_flag_payload(flag_key, distinct_id) or {}

    if isinstance(payload, str):
        payload = json.loads(payload)

    show("Payload", json.dumps(payload, indent=2))

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{flag_key} payload must be JSON with prompt_name and prompt_version"
        )
    if "prompt_version" not in payload:
        raise RuntimeError(f"{flag_key} payload must include prompt_version")

    prompt_name = payload.get("prompt_name") or env("POSTHOG_PROMPT_NAME")
    prompt_version = int(payload["prompt_version"])
    prompt = prompts.get(prompt_name, version=prompt_version)
    system_prompt = prompts.compile(prompt, {})
    show("System prompt", system_prompt)

    posthog.capture(
        distinct_id=distinct_id,
        event="$ai_generation",
        properties={
            "$ai_trace_id": trace_id,
            "$ai_model": "gpt-5-mini",
            "$ai_provider": "openai",
            "$ai_input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "$ai_input_tokens": 10,
            "$ai_output_choices": [{"role": "assistant", "content": mock_response}],
            "$ai_output_tokens": 20,
            "$ai_latency": round(random.uniform(0.3, 2.5), 3),
            "$ai_total_cost_usd": round(random.uniform(0.0001, 0.005), 6),
            "$ai_prompt_name": prompt_name,
            "$ai_prompt_version": prompt_version,
        },
    )

    posthog.capture(
        distinct_id=distinct_id,
        event="$ai_evaluation",
        properties={
            "$ai_trace_id": trace_id,
            "$ai_evaluation_result": random.choice([True, False]),
            "$ai_prompt_name": prompt_name,
            "$ai_prompt_version": prompt_version,
        },
    )

    show("Mock response", mock_response)

posthog.shutdown()
