# ai_events Migration Manual Testing Checklist

Run `test_ai_events_migration.py --batch-label <Sx>` at each state to generate tagged events.

---

## S1: Post-deploy, pre-write (flag OFF, splitting OFF)

**Setup:** Deploy branch with bug fix. No config changes.
**Script:** `python test_ai_events_migration.py --batch-label S1`

| # | Screen | Action | Expected |
|---|--------|--------|----------|
| 1 | Generations | Open, look for S1 events | Events visible (reads `events`) |
| 2 | Traces list | Open, look for S1 traces | Traces visible with correct latency/tokens/costs |
| 3 | Single trace | Click into S1-nested-trace | Span hierarchy renders, heavy props visible |
| 4 | Trace nav | Click next/prev arrows | Navigation works between S1 traces |
| 5 | Errors | Open | S1 error traces visible (reads `events`, flag OFF) |
| 6 | Tools | Open | S1 tool traces visible (reads `events`, flag OFF) |
| 7 | Tools heatmap | Toggle to heatmap view | Works (always reads `events`) |
| 8 | Eval summary | Trigger evaluation summary | Works (reads `events`, flag OFF) |

**This is the baseline.** Everything reads from `events`.

---

## S2: Dual-write, flag OFF

**Setup:** Set `INGESTION_AI_EVENT_SPLITTING_ENABLED=true`, restart ingestion.
**Script:** `python test_ai_events_migration.py --batch-label S2`

| # | Screen | Action | Expected |
|---|--------|--------|----------|
| 1 | Generations | Look for S2 events | Visible (reads `events`, flag still OFF) |
| 2 | Single trace | Open S2-heavy-props-trace | Heavy properties visible from `events` |
| 3 | Errors | Open | S1 + S2 error traces visible (reads `events`, flag OFF) |
| 4 | Tools | Open | S1 + S2 tool traces visible (reads `events`, flag OFF) |

**Skip:** Traces list, trace nav, eval runs, eval summary — same as S1.

---

## S3: Dual-write + flag ON (the big switch)

**Setup:** Enable `ai-events-table-rollout` feature flag for the test team.
**No new data needed** — S2 data is in both tables.

| # | Screen | Action | Expected |
|---|--------|--------|----------|
| 1 | Generations | Look for S2 events | Still visible (**now reads `ai_events`**) |
| 2 | Traces list | Open | S2 traces visible (**now reads `ai_events`**). Same counts as S2. |
| 3 | Single trace | Open S2-heavy-props-trace | Heavy properties visible via `merge_heavy_properties()` — compare to S2, must be identical |
| 4 | Single trace | Open S2-nested-trace | Span hierarchy correct. Latency rollup matches S2. |
| 5 | Single trace | Open S2-error-trace | Error banner/indicator shows correctly |
| 6 | Trace nav | Next/prev on S2 traces | Works via `ai_events` |
| 7 | Eval runs | Click "Run evaluation" on S2 generation | Triggers successfully, reads from `ai_events` |
| 8 | Errors | Open | **Now reads `ai_events`** — shows only S2 errors (S1 only in `events`). |
| 9 | Tools | Open | **Now reads `ai_events`** — shows only S2 tool traces. |
| 10 | Eval summary | Trigger eval summary | **Now reads `ai_events`** — works for S2 evaluations |

**Key:** Compare S3 trace detail vs S2 trace detail for the same trace. Must be identical.

**Expected gap:** Errors/tools/eval tabs will only show S2+ data (dual-written). S1-only data is in `events` only.

---

## S4: Strip heavy + flag ON

**Setup:** Set `INGESTION_AI_EVENT_SPLITTING_STRIP_HEAVY=true`, restart ingestion.
**Script:** `python test_ai_events_migration.py --batch-label S4`

| # | Screen | Action | Expected |
|---|--------|--------|----------|
| 1 | Single trace | Open S4-heavy-props-trace | Heavy properties visible from `ai_events` |
| 2 | HogQL debug | `SELECT properties FROM events WHERE uuid = '<S4-heavy-uuid>'` | `$ai_input`, `$ai_output`, `$ai_output_choices`, `$ai_input_state`, `$ai_output_state`, `$ai_tools` **ABSENT** |
| 3 | HogQL debug | `SELECT input, output FROM ai_events WHERE uuid = '<S4-heavy-uuid>'` | Heavy columns have full data |
| 4 | Generations | Look for S4 events | Visible with full data |
| 5 | Errors | S4 error trace visible | Yes |
| 6 | Tools | S4 tools trace visible | Yes |
| 7 | Tools heatmap | Check S4 events | Works — `$ai_tools_called` is NOT a heavy property |

---

## S5: Rollback (flag OFF, strip OFF)

**Setup:** Disable `ai-events-table-rollout` flag. Set `STRIP_HEAVY=false`, restart ingestion.
**Script:** `python test_ai_events_migration.py --batch-label S5`

| # | Screen | Action | Expected |
|---|--------|--------|----------|
| 1 | Single trace | Open S4-heavy-props-trace | **Heavy properties MISSING** — reads `events` which was stripped |
| 2 | Single trace | Open S5-heavy-props-trace | Heavy properties visible (not stripped) |
| 3 | Single trace | Open S2-heavy-props-trace | Heavy properties visible (not stripped) |
| 4 | Generations | Look for S4 events | Visible but input/output columns empty |
| 5 | Generations | Look for S5 events | Visible with full data |
| 6 | Errors | Open | Shows errors from S2, S4, S5 |
| 7 | Tools | Open | Shows tools from S2, S4, S5 |
| 8 | **Recover** | Re-enable flag | S4 heavy properties restored (reads `ai_events`) |

**Key:** This demonstrates why the flag should not be turned OFF after stripping is enabled.

---

## Automated Tests

```bash
pytest posthog/hogql_queries/ai/test/ -v
pytest posthog/hogql/database/test/test_database.py -v -k "ai_events"
pytest posthog/models/ai_events/ -v
cd nodejs && pnpm jest split-ai-events-step.test.ts
```

## Known Issues

- **Data gap after flag ON:** Errors/tools/eval summary only show dual-written data (S2+). Pre-dual-write data (S1) is only in `events`. Backfill (Phase 4) addresses this.
- **Tools heatmap:** Always reads `events`. After stripping (S4), `$ai_tools_called` is still present (not a heavy property).
- **TTL boundary:** If test data is older than 31 days, flag-gated features fall back to `events` even with flag ON.
