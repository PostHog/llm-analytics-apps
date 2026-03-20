# OTel → PostHog mapping: E2E testing reference

This document describes how OTel spans from AI frameworks are ingested into
PostHog as LLM analytics events, and how to write E2E tests that verify the
mapping. Scenarios use **Pydantic AI** as a concrete example, but the pipeline
stages and verification patterns apply to any OTel-instrumented framework
(LangChain, Vercel AI, etc.).

---

## Pipeline overview

OTel spans flow through three stages before becoming PostHog events:

1. **Rust layer** — per-span, during HTTP ingestion
2. **Node.js layer** — per-event, after Kafka
3. **Framework middleware** — per-event, only when a known framework is detected

Stages 1–2 handle the **standard OTel GenAI semantic conventions** and should
work for any compliant framework. Stage 3 is framework-specific middleware.

### Design principle: keep middleware thin

Different frameworks implement different versions of the OTel GenAI semantic
conventions. The attribute names in stages 1–2 (e.g. `gen_ai.input.messages`,
`gen_ai.usage.input_tokens`) are from the spec, but not every framework emits
every attribute — and some use older or slightly different names.

**The goal is to handle spec version differences in the shared layers (1–2),
not in per-framework middleware.** If a framework uses a different attribute
name for something that's just a version difference in the GenAI spec (e.g.
an older name for token counts), add a fallback in the shared mapping layer.
Middleware (stage 3) should only handle things that are truly
framework-specific and not part of any version of the spec — like Pydantic
AI's `pydantic_ai.all_messages` or `logfire.msg`.

In practice:
- **Spec-version differences** (different attribute names for the same concept)
  → handle in stages 1–2 with fallbacks
- **Framework-specific custom attributes** (not in any version of the spec)
  → handle in stage 3 middleware

---

## Stage 1: Rust layer (fan_out.rs)

Runs per-span during ingestion at `/i/v0/ai/otel`.

| Source | PostHog property | Notes |
|---|---|---|
| OTel trace ID (hex) | `$ai_trace_id` | |
| OTel span ID (hex) | `$ai_span_id` | |
| OTel parent span ID (hex) | `$ai_parent_id` | Only if non-empty |
| `gen_ai.operation.name` | determines event name | `"chat"` → `$ai_generation`, `"embeddings"` → `$ai_embedding`, else `$ai_span` |
| OTel span `name` field | `$otel_span_name` | Intermediate, renamed later |
| OTel start/end nanos | `$otel_start_time_unix_nano` / `$otel_end_time_unix_nano` | Intermediate, used for latency |
| constant | `$ai_ingestion_source` = `"otel"` | |
| All resource + span attributes | passthrough | Merged into properties |

---

## Stage 2: Node.js layer (attribute-mapping.ts)

Runs on every OTel event after Kafka. The attributes listed below are from the
OTel GenAI semantic conventions. Not every framework emits all of them, and
some frameworks may use older attribute names from earlier spec versions.
When a framework uses a different name for the same concept, prefer adding a
fallback here rather than in framework middleware.

| OTel attribute | PostHog property | Notes |
|---|---|---|
| `gen_ai.input.messages` | `$ai_input` | JSON-parsed if string |
| `gen_ai.output.messages` | `$ai_output_choices` | JSON-parsed if string |
| `gen_ai.usage.input_tokens` | `$ai_input_tokens` | |
| `gen_ai.usage.output_tokens` | `$ai_output_tokens` | |
| `gen_ai.request.model` | `$ai_model` | |
| `gen_ai.provider.name` | `$ai_provider` | Primary |
| `gen_ai.system` | `$ai_provider` | Fallback (if primary absent) |
| `gen_ai.response.model` | `$ai_model` | Fallback (if primary absent) |
| `server.address` | `$ai_base_url` | |
| `telemetry.sdk.name` | `$ai_lib` | |
| `telemetry.sdk.version` | `$ai_lib_version` | |
| `$otel_span_name` | `$ai_span_name` | |
| computed from nanos | `$ai_latency` | Seconds (float) |
| `$ai_span` with no parent | promoted to `$ai_trace` | Root span promotion |

**Stripped** after processing:
`telemetry.sdk.language`, `gen_ai.operation.name`, `posthog.ai.debug`

---

## Stage 3: Framework middleware

Each supported framework has a middleware in `index.ts` that runs when the
framework is detected. Middleware handles attributes that are **truly
framework-specific** — custom attributes not found in any version of the OTel
GenAI spec. It normalises them into the common PostHog schema
(`$ai_input_state`, `$ai_output_state`, `$ai_span_name`) and deletes the raw
originals.

If a new framework emits standard GenAI attributes (even from a different spec
version), those should be handled by adding fallbacks in stage 2. Middleware
should only be needed for the framework's custom, non-standard attributes.

### Pydantic AI middleware (example)

Only runs when provider is detected as `pydantic-ai`. The attributes handled
here (`pydantic_ai.all_messages`, `final_result`, `logfire.*`) are all custom
to Pydantic AI / Logfire and not part of the OTel GenAI spec.

**On `$ai_trace`:**

| Source | PostHog property | Notes |
|---|---|---|
| First `role: "user"` in `pydantic_ai.all_messages` | `$ai_input_state` | Custom: full message history |
| `final_result` or last non-user/system message | `$ai_output_state` | Custom: `final_result` takes priority |
| `gen_ai.agent.name` or `agent_name` | `$ai_span_name` | Custom: agent naming |

Deleted: `pydantic_ai.all_messages`, `final_result`, `agent_name`, `gen_ai.agent.name`

**On `$ai_span`:**

| Source | PostHog property | Notes |
|---|---|---|
| `tool_arguments` | `$ai_input_state` | Custom: Pydantic AI tool format |
| `tool_response` | `$ai_output_state` | Custom: Pydantic AI tool format |
| `gen_ai.tool.name` | `$ai_span_name` | |

Deleted: `tool_arguments`, `tool_response`, `gen_ai.tool.name`, `gen_ai.tool.call.id`

**Always deleted:** `logfire.json_schema`, `logfire.msg`, `operation.cost`

### Writing middleware for a new framework

Before writing middleware, check whether the framework's attributes are:
1. **Standard GenAI spec attributes** (possibly from a different version)
   → add fallbacks in stage 2 instead
2. **Custom framework-specific attributes** → write middleware

A new middleware needs to:
1. **Detect** the framework (via `gen_ai.system`, specific attributes, etc.)
2. **Map** only custom attributes → `$ai_input_state`, `$ai_output_state`, `$ai_span_name`
3. **Delete** the raw originals so they don't pollute top-level properties

---

## Debug mode

When resource attribute `posthog.ai.debug` is truthy:
- `$ai_debug` = `true`
- `$ai_debug_data` = snapshot of all raw properties before any remapping

---

## Example scenarios (Pydantic AI)

The scenarios below use Pydantic AI to illustrate common patterns. When testing
a different framework, expect the same general span shapes (trace → generation,
trace → tool → generation, etc.) but with framework-specific attribute names
and span naming conventions.

### Scenario 1: Simple generation (no tools)

**Setup:** system prompt + single user message, no tools.

**Expected spans (2):**

```
$ai_trace: "agent run"
  └─ $ai_generation: "chat gpt-4o-mini"
```

#### $ai_trace

| Property | Expected |
|---|---|
| `$ai_input_state` | First user message object (`role: "user"`) |
| `$ai_output_state` | Assistant reply (from `final_result` or last message) |
| `$ai_span_name` | Agent name (from `gen_ai.agent.name`) |
| `$ai_latency` | > 0 |
| `$ai_lib` | `"opentelemetry"` |
| `$ai_trace_id` | Present |
| `$ai_parent_id` | **Absent** (root span) |

Must be absent at top level:
`pydantic_ai.all_messages`, `final_result`, `gen_ai.operation.name`,
`telemetry.sdk.language`, `logfire.*`

#### $ai_generation

| Property | Expected |
|---|---|
| `$ai_input` | Array: [system message, user message] |
| `$ai_output_choices` | Array: [assistant reply] |
| `$ai_model` | `"gpt-4o-mini"` |
| `$ai_provider` | `"openai"` |
| `$ai_base_url` | `"api.openai.com"` or similar |
| `$ai_input_tokens` | > 0 |
| `$ai_output_tokens` | > 0 |
| `$ai_latency` | > 0 |
| `$ai_parent_id` | = trace's `$ai_span_id` |

Must be absent: `gen_ai.operation.name`, `telemetry.sdk.language`, `logfire.*`

---

### Scenario 2: Single tool call

**Setup:** weather tool, expects LLM to call it once then summarise.

**Expected spans (5):**

```
$ai_trace: "agent run"
  ├─ $ai_generation (1st → tool_call finish reason)
  ├─ $ai_span: "running 1 tool"
  │   └─ $ai_span: "get_weather"
  └─ $ai_generation (2nd → final answer)
```

#### Verifications

- **Trace:** `$ai_output_state` contains weather summary
- **1st generation:** `$ai_output_choices` contains tool_call with `get_weather`
- **Tool wrapper:** `$ai_span_name` = `"running 1 tool"` (Pydantic AI-specific, from `logfire.msg`)
- **Tool span:** `$ai_span_name` = `"get_weather"`, `$ai_input_state` = tool args,
  `$ai_output_state` = weather string
- **2nd generation:** `$ai_input` includes tool result in conversation
- All 5 events share same `$ai_trace_id`
- Parent chain: generations → trace, tool → wrapper → trace

Must be absent on tool spans:
`tool_arguments`, `tool_response`, `gen_ai.tool.name`

---

### Scenario 3: Multiple tool calls in one turn

**Setup:** same weather tool, prompt asks to compare two cities.

**Expected spans (7+):**

```
$ai_trace: "agent run"
  ├─ $ai_generation (1st → 2 tool_calls)
  ├─ $ai_span: "running 2 tools"
  │   ├─ $ai_span: "get_weather" (city A)
  │   └─ $ai_span: "get_weather" (city B)
  └─ $ai_generation (2nd → comparison)
```

#### Verifications

- Tool wrapper: `$ai_span_name` = `"running 2 tools"`
- Two tool spans with different `$ai_input_state` (different lat/lng)
- Both tool spans share the same parent (the wrapper)
- Final generation's `$ai_input` includes both tool results

---

### Scenario 4: Structured output

**Setup:** returns a Pydantic `CityInfo` model via tool-call mechanism.

**Expected spans (2):**

```
$ai_trace: "agent run"
  └─ $ai_generation: "chat gpt-4o-mini"
```

#### Verifications

- Generation `$ai_output_choices` contains a structured tool call
  (Pydantic AI uses tool calls to enforce structured output)
- Trace `$ai_output_state` = the structured result as dict/JSON
- `final_result` absent from top-level (moved to `$ai_output_state`, raw in `$ai_debug_data`)

---

### Scenario 5: Tool retry

**Setup:** tool raises `ModelRetry` on first call, succeeds on second.
(Other frameworks may handle retries differently.)

**Expected spans (7+):**

```
$ai_trace: "agent run"
  ├─ $ai_generation (1st → tool_call)
  ├─ $ai_span: "running 1 tool"
  │   └─ $ai_span: "find_user" (fails with ModelRetry)
  ├─ $ai_generation (2nd → retried tool_call)
  ├─ $ai_span: "running 1 tool"
  │   └─ $ai_span: "find_user" (succeeds)
  └─ $ai_generation (3rd → final answer)
```

#### Verifications

- First tool span may have error attributes or retry message in output
- Multiple generation spans (LLM re-invoked after retry)
- Trace completes successfully (`$ai_is_error` absent or false)
- `$ai_output_state` on trace = final successful result

---

### Scenario 6: Unrecoverable error

**Setup:** tool raises an unhandled exception. Agent should error.

**Expected spans:**

```
$ai_trace: "agent run" (error status)
  ├─ $ai_generation (tool_call with b=0)
  ├─ $ai_span: "running 1 tool"
  │   └─ $ai_span: "divide" (ERROR)
  └─ ... (depends on retry behavior)
```

#### Verifications

- Tool span has error indicators
- Trace may have `$ai_is_error` = true
- Error details preserved in properties

---

### Scenario 7: Minimal agent

**Setup:** no tools, no system prompt.

**Expected spans (2):**

```
$ai_trace: "agent run"
  └─ $ai_generation: "chat gpt-4o-mini"
```

#### Verifications

- Same as scenario 1 but no system prompt in generation `$ai_input`
- Trace has no tools attribute
- Absent system prompt doesn't break mapping

---

### Scenario 8: Multi-turn conversation

**Setup:** two sequential calls, second passes message history.

**Expected spans (4, two separate traces):**

```
Trace 1: "agent run"
  └─ $ai_generation

Trace 2: "agent run"
  └─ $ai_generation
```

#### Verifications

- Two different `$ai_trace_id` values
- Turn 2 generation's `$ai_input` includes full history
  (system + turn 1 messages + turn 2 user message)
- Turn 2 trace's `$ai_input_state` = turn 2 user message ("What's my name?")
- Turn 2 response should contain "Carlos"
- Turn 2 `$ai_input_tokens` > turn 1 (longer context)

---

### Scenario 9: Agent delegation

**Setup:** main agent delegates to a sub-agent via a tool.

**Expected spans (7+, nested):**

```
$ai_trace: "agent run" (main)
  ├─ $ai_generation (main 1st → tool_call research)
  ├─ $ai_span: "running 1 tool"
  │   └─ $ai_span: "research"
  │       └─ $ai_trace(?): "agent run" (sub-agent)
  │           └─ $ai_generation (sub-agent call)
  └─ $ai_generation (main 2nd → final answer)
```

#### Verifications

- Nested agent run appears as child within the tool span
- Both agents produce generation events with different `$ai_input`
- Token counts from sub-agent are separate
- Whether the sub-agent shares the parent trace or starts a new one
  depends on OTel context propagation (framework-specific)

---

### Scenario 10: Dynamic system prompt

**Setup:** system prompt computed from runtime dependencies (`deps="Carlos"`).

**Expected spans (2):**

```
$ai_trace: "agent run"
  └─ $ai_generation: "chat gpt-4o-mini"
```

#### Verifications

- Generation `$ai_input` includes dynamic system prompt containing "Carlos"
- No extra spans from dependency injection
- Response references "Carlos"

---

### Scenario 11: Alternate provider (Anthropic)

**Setup:** uses Anthropic Claude instead of OpenAI. Skipped if `ANTHROPIC_API_KEY` not set.

**Expected spans (2):**

```
$ai_trace: "agent run"
  └─ $ai_generation: "chat claude-sonnet-4-5-20250929"
```

#### Verifications

| Property | Expected |
|---|---|
| `$ai_provider` | `"anthropic"` |
| `$ai_model` | `"claude-sonnet-4-5-20250929"` |
| `$ai_base_url` | Anthropic API address |

- Trace structure identical to OpenAI scenarios
- Cost calculation works for Anthropic model

---

## Global verification checklist

For **every** scenario (regardless of framework), check:

- [ ] Trace appears as `$ai_trace` (not a synthetic pseudo-trace)
- [ ] `$ai_trace_id` is consistent across all events in the trace
- [ ] `$ai_parent_id` chain is correct (generations → trace, tools → wrapper → trace)
- [ ] `$ai_latency` present and > 0 on all events
- [ ] `$ai_span_name` set on all events
- [ ] `$ai_lib` = `"opentelemetry"` and `$ai_lib_version` present
- [ ] `$ai_provider` = `"openai"` (or `"anthropic"`, etc.) on generations
- [ ] `$ai_base_url` present on generations
- [ ] `$ai_model` present on generations
- [ ] `$ai_input_tokens` and `$ai_output_tokens` present on generations
- [ ] `$ai_input` and `$ai_output_choices` present on generations (parsed JSON arrays)
- [ ] Cost calculated (`$ai_total_cost_usd` > 0 on generations)
- [ ] Trace `$ai_input_state` = first user message
- [ ] Trace `$ai_output_state` = final result
- [ ] Tool spans have `$ai_input_state` (args) and `$ai_output_state` (result)
- [ ] Timeline view shows correct tree hierarchy

**Framework-specific raw attributes must be absent** from top-level properties
after middleware processing. For Pydantic AI:

- [ ] `pydantic_ai.all_messages` (only in `$ai_debug_data`)
- [ ] `final_result` (only in `$ai_debug_data`)
- [ ] `telemetry.sdk.language`
- [ ] `gen_ai.operation.name`
- [ ] `logfire.json_schema`, `logfire.msg`
- [ ] `tool_arguments`, `tool_response` (on tool spans)

---

## Known edge cases

### Spec version differences across frameworks

Different frameworks implement different versions of the OTel GenAI semantic
conventions. Common differences include:

- **Attribute names for the same concept** — e.g. token count attributes may
  use different names across spec versions. These should be handled as
  fallbacks in stage 2, not in middleware.
- **Missing attributes** — a framework may not emit all attributes from the
  spec (e.g. no `server.address`). Tests should verify what the framework
  actually sends rather than assuming all spec attributes are present.
- **Extra non-spec attributes** — frameworks may add their own attributes
  (e.g. `logfire.msg`, `pydantic_ai.all_messages`). These are what middleware
  should handle.

When a new framework doesn't produce a PostHog property you expect, first
check whether it's using a different attribute name for the same concept. If
so, add a fallback in the shared mapping layer rather than special-casing it
in middleware.

### Other edge cases

- **Structured output via tool calls:**
  Some frameworks (e.g. Pydantic AI) enforce result types by injecting a hidden tool call.
  The generation's `$ai_output_choices` will show a tool_call, not plain text.
- **Retries vs regular exceptions:**
  Framework-managed retries (e.g. Pydantic AI's `ModelRetry`) are caught and retried;
  regular exceptions may propagate and mark the trace as errored.
- **Sub-agent trace nesting:**
  Whether a sub-agent creates a new trace or inherits the parent
  depends on OTel context propagation. This is framework-specific.
- **Fallback span names:**
  When `$otel_span_name` is empty, framework-specific attributes (e.g. `logfire.msg`
  for Pydantic AI) may be used as `$ai_span_name`.
- **`gen_ai.system` vs `gen_ai.provider.name`:**
  Provider detection checks `gen_ai.system` first, then `gen_ai.provider.name`,
  then falls back to heuristic attribute detection (framework-specific attributes).

---

## How to run (Pydantic AI example)

```bash
cd llm-analytics-apps
uv sync

# All scenarios
uv run scripts/test_pydantic_ai_otel.py

# Specific scenarios
uv run scripts/test_pydantic_ai_otel.py 2 5

# With debug mode (captures raw pre-mapping properties)
DEBUG=1 uv run scripts/test_pydantic_ai_otel.py
```

After running, wait ~30s for ingestion, then open PostHog → LLM analytics → Traces.
