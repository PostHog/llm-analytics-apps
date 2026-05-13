import json
import os
from pathlib import Path

from dotenv import load_dotenv
from posthog import Posthog
from posthog.ai.openai import OpenAI
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
    host=env("POSTHOG_HOST", "https://us.posthog.com"),
    personal_api_key=env("POSTHOG_PERSONAL_API_KEY"),
    feature_flags_request_timeout_seconds=3,
)

distinct_id = env("POSTHOG_DISTINCT_ID", "toy-user")
flag_key = env("POSTHOG_PROMPT_CONFIG_FLAG_KEY")
flags = posthog.evaluate_flags(distinct_id, flag_keys=[flag_key])
flag_value = flags.get_flag(flag_key)
payload = flags.get_flag_payload(flag_key) or {}
if isinstance(payload, str):
    payload = json.loads(payload)

show("Feature flag", f"{flag_key} = {flag_value!r}")
show("Payload", json.dumps(payload, indent=2))

if not isinstance(payload, dict):
    raise RuntimeError(f"{flag_key} payload must be JSON with prompt_name and prompt_version")
if "prompt_version" not in payload:
    raise RuntimeError(f"{flag_key} payload must include prompt_version")

prompt_name = payload.get("prompt_name") or env("POSTHOG_PROMPT_NAME")
prompt_version = int(payload["prompt_version"])
prompts = Prompts(posthog)
prompt = prompts.get(prompt_name, version=prompt_version)
system_prompt = prompts.compile(prompt, {})
show("System prompt", system_prompt)

client = OpenAI(api_key=env("OPENAI_API_KEY"), posthog_client=posthog)
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": system_prompt},
    ],
    posthog_distinct_id=distinct_id,
    posthog_properties={
        "$ai_prompt_name": prompt_name,
        "$ai_prompt_version": prompt_version
    },
)

show("Response", response.choices[0].message.content)
posthog.shutdown()
