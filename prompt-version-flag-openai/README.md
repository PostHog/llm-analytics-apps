# Prompt Version Flag OpenAI Toy App

Tiny Python example that:

1. reads config from `prompt-version-flag-openai/.env`
2. evaluates `POSTHOG_PROMPT_CONFIG_FLAG_KEY` for `POSTHOG_DISTINCT_ID`
3. reads `prompt_name` and `prompt_version` from that flag's payload
4. requires `prompt_version` in the flag payload and falls back to `POSTHOG_PROMPT_NAME` only if `prompt_name` is omitted
5. fetches that prompt version from PostHog Prompt Management
6. sends one OpenAI chat completion through PostHog's OpenAI wrapper

Example feature flag payload:

```json
{
  "prompt_name": "support-system-prompt",
  "prompt_version": 6
}
```

```bash
cp prompt-version-flag-openai/.env.example prompt-version-flag-openai/.env
# fill in the keys and names
uv run python prompt-version-flag-openai/app.py
```

Use an app host for `POSTHOG_HOST`, such as `https://us.posthog.com` or `https://eu.posthog.com`, because Prompt Management reads from the app API.

If you see requests going to `localhost:80`, your `POSTHOG_HOST` is pointing at localhost without the PostHog app port. Use `http://localhost:8010` for a local PostHog app, or a cloud host such as `https://us.posthog.com`.
