# Logger Audit Report — Logging vs Landscape Separation

**Date:** 2026-03-11
**Branch:** RC4-user-interface
**Scope:** All `structlog` and `logging` usage in `src/elspeth/`

## Context

ELSPETH maintains two complementary visibility systems:

- **Landscape** — the legal audit trail. Complete lineage, persisted forever, source of truth. "If it's not recorded, it didn't happen."
- **Logging** — operational visibility. Real-time, ephemeral, for dashboards and operator alerting. Never the source of truth for row outcomes.

This audit inventoried all 42 files with logger usage to verify the boundary is clean: logging should never be the *only* record of a row-affecting decision, and should never duplicate what Landscape already captures without justification.

## Inventory Summary

| Layer | Files with loggers | Assessment |
|-------|-------------------|------------|
| L0 contracts/ | 2 | Edge cases — telemetry failure, contract field skips |
| L1 core/ | 7 | Mostly meta-audit (journal failures, state guard). Clean. |
| L2 engine/ | 7 | Mix of redundant echoes and audit gaps (see below) |
| L3 plugins/ | 16 | External boundary logging (Tier 3 calls). Correct. |
| L3 telemetry/ | 6 | Self-monitoring. Correct — can't audit telemetry in Landscape. |
| L3 testing/mcp/tui/cli | 5 | Infrastructure and UI. Correct. |

## Findings

### Category A: Audit Gaps — Logged But Not in Landscape

These are row-affecting decisions or metadata where the log is the *only* record. An auditor querying Landscape alone cannot reconstruct what happened.

#### A1. LLM Transform `success_reason` Too Generic

**Files:** `plugins/transforms/llm/transform.py` (lines 334, 729-733, 837-840)

**Problem:** When an LLM classification succeeds, `success_reason` contains only:

```python
# SingleQueryStrategy (line 334)
success_reason={"action": "enriched", "fields_added": [self.response_field]}

# MultiQueryStrategy (lines 729, 837)
success_reason={"action": "multi_query_enriched", "queries_completed": len(self.query_specs)}
```

The actual classification result (category, confidence, model response metadata) is written into the output row data but **not** into `success_reason`. This means:

- An auditor can see "row was enriched" but not *how* it was enriched without parsing the full output payload
- If the output payload is purged (retention policy), the classification decision is **permanently lost** — only the generic "enriched" label survives
- Multi-query transforms don't record per-query success/failure breakdown — "2 of 3 queries succeeded" is indistinguishable from "3 of 3 succeeded"

**Risk:** Medium. The output row *does* contain the result, so pre-purge the data is recoverable. Post-purge, only the hash survives — you can verify integrity but not reconstruct the decision.

**Remediation:** Enrich `success_reason` with semantic metadata:

```python
# SingleQuery — include response summary
success_reason={
    "action": "enriched",
    "fields_added": [self.response_field],
    "model": model_name,
    "response_tokens": usage.completion_tokens,  # already available from call audit
}

# MultiQuery — include per-query outcomes
success_reason={
    "action": "multi_query_enriched",
    "queries_completed": len(completed),
    "queries_failed": len(failed),
    "query_outcomes": {spec.name: "success" | "error" for spec in self.query_specs},
}
```

**Note:** The call-level audit (calls table) already records model, tokens, and latency. The gap is specifically in `success_reason` not summarizing the *interpretation* of the response — the downstream meaning assigned to the LLM output.

#### ~~A2. Coalesce Union Merge Field Collisions~~ → Reclassified as R3

**File:** `engine/coalesce_executor.py` (line 833)

**Original assessment:** Classified as audit gap — collision metadata logged but not recorded.

**Correction (2026-03-13):** Investigation found that `CoalesceMetadata.with_collisions()` (line 758-759) already records union field collision data in `context_after_json` via `CoalesceMetadata.union_field_collisions`. The `slog.warning("union_merge_field_collisions", ...)` at line 832 is redundant — it duplicates data already in the audit trail.

**Action taken:** Warning log removed (logger hygiene plan, Task 3). MCP collision query analyzer filed as follow-up (`elspeth-ce1b20bb31`) to replace push observability (log-based alerting) with pull (Landscape query via MCP).

See: `docs/plans/2026-03-11-logger-hygiene-plan.md`

#### A3. Multi-Query Partial Failure Ambiguity

**File:** `plugins/transforms/llm/transform.py` (lines 729-733, 837-840)

**Problem:** When a multi-query transform completes with partial success (e.g., 2 of 3 queries succeeded), the success_reason records `queries_completed: 2` but not which queries failed or why. The row is marked `COMPLETED` with merged results from the successful queries.

**Risk:** Low-medium. The individual call records exist in the calls table, but correlating them back to a specific query spec requires joining on token_id + call metadata. A summary in success_reason would make this queryable.

**Remediation:** Covered by A1 remediation (per-query outcomes in success_reason).

---

### Category B: Redundant Logging — Duplicates Landscape

These log events echo information already captured in the audit trail. They are not harmful but create a temptation to query logs instead of Landscape.

#### B1. `pipeline_row_created` Debug Log

**File:** `engine/executors/transform.py` (line 418)

```python
slog.debug(
    "pipeline_row_created",
    token_id=token.token_id,
    transform=transform.name,
    contract_mode=result.row.contract.mode,
)
```

**Already in Landscape:** `node_states` records token_id, node_id (maps to transform), and the complete result. Contract mode is embedded in the row data.

**Recommendation:** Remove. This is debug noise from development that survived into production code. The `node_states` record is the authoritative source.

#### B2. Payload Purge Notices

**File:** `core/landscape/execution_repository.py` (lines 160, 1010)

- Line 160: `logger.warning()` when quarantined input is not canonically hashable (uses repr_hash fallback)
- Line 1010: `logger.debug("Call response payload purged")` when PayloadNotFoundError on retrieval

**Already in Landscape:**
- Line 160: The input_hash (fallback or canonical) is stored in node_states. The *kind* of hash is not distinguished.
- Line 1010: `CallDataState.PURGED` is returned and recorded.

**Recommendation:**
- Line 160: **Keep** — this warns about degraded audit precision (repr_hash vs canonical_hash). Consider adding a `hash_method` field to node_states instead.
- Line 1010: **Remove** — the return value already signals the state. Debug log adds nothing.

#### B3. Purge Operation Warnings

**File:** `core/retention/purge.py` (lines 355, 368, 402)

```python
# Line 355: payload existence check failed (OSError)
# Line 368: payload deletion failed (OSError)
# Line 402: grade update failed after purge
```

**Assessment:** These are *not* redundant — purge is a post-run management operation. Landscape records what was purged (payload_refs, retention grades) but not I/O failures during the purge process itself. These warnings are **correctly placed** as operational logging.

**Recommendation:** Keep. Reclassified from "redundant" to "correctly operational."

---

### Category C: Meta-Audit Logging — Correctly Placed

These log about failures in the audit system itself. Logging is the only option when Landscape is the thing that's broken.

| File | Event | Why logging is correct |
|------|-------|----------------------|
| `core/landscape/journal.py:141-183` | Journal write failures, recovery | Backup for when Landscape can't write |
| `engine/executors/state_guard.py:129,161` | Failed to record terminal state | Tier 1 violation — can't audit the audit failure |
| `engine/executors/sink.py:380` | Post-sink checkpoint callback failed | Durable write succeeded; checkpoint is best-effort |
| `core/operations.py:175` | Failed to complete operation record | Critical: audit write itself failed |

**Recommendation:** No changes. These are architecturally necessary.

---

### Category D: Correctly Separated Operational Logging

These log operational concerns that don't belong in Landscape.

| Layer | Files | What they log |
|-------|-------|---------------|
| L3 telemetry/ (6 files) | Exporter health, queue status, init | Telemetry about telemetry |
| L3 plugins/infrastructure/ | Plugin init, rollback, late result eviction | Plugin lifecycle |
| L3 plugins/transforms/llm/ | API retries, rate limits, provider warnings | Tier 3 boundary observations |
| L3 plugins/infrastructure/clients/ | HTTP/LLM client retries, timeouts | External call operational details |
| L1 core/rate_limit/ | Thread cleanup suppression | Benign infrastructure |
| L0 contracts/ | Telemetry emit failure, contract field skips | Edge cases |
| L3 testing/ | ChaosLLM/ChaosWeb server activity | Test infrastructure |
| L3 mcp/, tui/, cli | Server/UI operational warnings | Application layer |

**Recommendation:** No changes. These follow the correct pattern: calls are in Landscape (calls table), operational details are in logs.

---

## Proposed Work Items

### Phase 1: Remove Redundant Logging (Small, Low Risk)

| ID | Action | File | Lines | Effort | Status |
|----|--------|------|-------|--------|--------|
| R1 | Remove `pipeline_row_created` debug log | `engine/executors/transform.py` | 418-423 | Trivial | **Done** |
| R2 | Remove `Call response payload purged` debug log | `core/landscape/execution_repository.py` | 1010 | Trivial | **Done** |
| R3 | Remove `union_merge_field_collisions` warning log (reclassified from G3) | `engine/coalesce_executor.py` | 832-837 | Trivial | **Done** |

### Phase 2: Close Audit Gaps (Medium, Requires Design)

| ID | Action | File | Effort | Status |
|----|--------|------|--------|--------|
| G1 | Enrich LLM single-query `success_reason` with model + token metadata | `plugins/transforms/llm/transform.py` | Small | **Done** |
| G2 | Enrich multi-query `success_reason` with model + fields_added | `plugins/transforms/llm/transform.py` | Medium | **Done** |
| ~~G3~~ | ~~Record union merge collision metadata in `context_after_json`~~ | — | — | Reclassified as R3 — data already recorded via `CoalesceMetadata.with_collisions()` |
| G4 | Evaluate adding `hash_method` to node_states for repr_hash fallback tracking | `core/landscape/execution_repository.py` | Design needed | Deferred |

### Phase 3: Investigate (Needs Decision)

| ID | Question | Context |
|----|----------|---------|
| I1 | Should coalesce checkpoint size warnings become Landscape metrics? | Currently log-only. Large checkpoints may indicate pipeline design issues. |
| I2 | Should LRU eviction of completed coalesce keys be auditable? | If a duplicate token arrives after eviction, the dedup check fails silently. |

---

## Design Considerations for Phase 2

### G1/G2: LLM `success_reason` Enrichment

The `success_reason` field flows to `node_states.success_reason_json` in Landscape. It's a `TransformSuccessReason` TypedDict defined in `contracts/errors.py`. Current fields:

```python
class TransformSuccessReason(TypedDict, total=False):
    action: str
    fields_added: list[str]
    queries_completed: int
    # ... other optional fields
```

**Constraints:**
- `success_reason` must be JSON-serializable (it's stored as JSON in SQLite/Postgres)
- Should not duplicate the full call audit (model, tokens, latency already in calls table)
- Should capture the *interpretation* — what the transform decided the LLM output meant
- Must not include raw LLM response content (may contain PII, subject to purge policy)

**Suggested additions:**
- `model`: str — which model produced the result (already in calls table, but useful for quick queries)
- `query_outcomes`: dict[str, str] — per-query success/error status for multi-query
- `response_summary`: dict — transform-specific interpretation metadata (e.g., classification label, confidence)

**Open question:** Should `response_summary` be a generic dict or should each transform subtype define its own schema? Generic is simpler but less queryable. Typed is more useful but couples the audit schema to plugin internals.

### ~~G3: Coalesce Collision Metadata~~ → Already implemented

**Correction (2026-03-13):** `CoalesceMetadata.with_collisions()` at `coalesce_executor.py:758-759` already records collision data in `context_after_json` as `union_field_collisions`. The original audit incorrectly assessed this as a gap. The warning log was the redundant item — removed as R3. MCP collision query analyzer filed as `elspeth-ce1b20bb31`.

---

## Appendix: Full File Inventory

### Files with structlog (35 files)

| File | Logger variable | Layer |
|------|----------------|-------|
| `core/landscape/journal.py` | `logger` | L1 |
| `core/landscape/execution_repository.py` | `logger` | L1 |
| `core/landscape/query_repository.py` | `logger` | L1 |
| `core/landscape/data_flow_repository.py` | `logger` | L1 |
| `core/rate_limit/limiter.py` | `logger` (local) | L1 |
| `core/retention/purge.py` | `logger` | L1 |
| `contracts/contract_propagation.py` | `log` | L0 |
| ~~`engine/executors/transform.py`~~ | ~~`slog`~~ | ~~L2~~ | *Removed (R1 — logger hygiene plan)* |
| `engine/executors/gate.py` | `slog` | L2 |
| `engine/executors/aggregation.py` | `slog` | L2 |
| `engine/coalesce_executor.py` | `slog` | L2 |
| `engine/orchestrator/core.py` | `slog` | L2 |
| `telemetry/factory.py` | `logger` | L3 |
| `telemetry/manager.py` | `logger` | L3 |
| `telemetry/exporters/console.py` | `logger` | L3 |
| `telemetry/exporters/otlp.py` | `logger` | L3 |
| `telemetry/exporters/datadog.py` | `logger` | L3 |
| `telemetry/exporters/azure_monitor.py` | `logger` | L3 |
| `plugins/infrastructure/manager.py` | `_logger` | L3 |
| `plugins/infrastructure/batching/mixin.py` | `_logger` | L3 |
| `plugins/infrastructure/clients/llm.py` | `logger` | L3 |
| `plugins/infrastructure/clients/http.py` | `logger` | L3 |
| `plugins/sources/azure_blob_source.py` | `logger` | L3 |
| `plugins/transforms/batch_replicate.py` | `logger` | L3 |
| `plugins/transforms/llm/provider.py` | `logger` | L3 |
| `plugins/transforms/llm/transform.py` | `logger` | L3 |
| `plugins/transforms/llm/multi_query.py` | `logger` | L3 |
| `plugins/transforms/llm/langfuse.py` | `logger` | L3 |
| `plugins/transforms/llm/azure_batch.py` | `logger` | L3 |
| `plugins/transforms/llm/providers/azure.py` | `logger` | L3 |
| `plugins/transforms/llm/providers/openrouter.py` | `logger` | L3 |
| `plugins/transforms/llm/openrouter_batch.py` | `_logger` | L3 |
| `plugins/transforms/azure/base.py` | `logger` | L3 |
| `testing/chaosllm/server.py` | `logger` | L3 |
| `testing/chaosllm/response_generator.py` | `logger` | L3 |
| `testing/chaosweb/server.py` | `logger` | L3 |
| `testing/chaosweb/content_generator.py` | `logger` | L3 |
| `tui/screens/explain_screen.py` | `logger` | L3 |

### Files with stdlib logging (9 files)

| File | Logger variable | Layer | Also has structlog? |
|------|----------------|-------|-------------------|
| `core/logging.py` | (config module) | L1 | Yes |
| `core/operations.py` | `logger` | L1 | No |
| `contracts/plugin_context.py` | `logger` | L0 | No |
| ~~`engine/executors/transform.py`~~ | ~~`logger`~~ | ~~L2~~ | *Removed (R1 — logger hygiene plan)* |
| `engine/executors/gate.py` | `logger` | L2 | Yes (`slog`) |
| `engine/executors/sink.py` | `logger` | L2 | No |
| `engine/executors/state_guard.py` | `logger` | L2 | No |
| `engine/executors/aggregation.py` | `logger` | L2 | Yes (`slog`) |
| `plugins/infrastructure/discovery.py` | `logger` | L3 | No |
| `mcp/server.py` | `logger` | L3 | No |

### Logger Variable Name Inconsistency

Three naming conventions are used:

| Convention | Count | Files |
|-----------|-------|-------|
| `logger` | 30 | Most files |
| `slog` | 5 | Engine executors, coalesce, orchestrator |
| `_logger` | 3 | Plugin manager, batching mixin, openrouter_batch |
| `log` | 1 | contract_propagation.py |

The `slog`/`logger` split in executors reflects dual stdlib+structlog usage (stdlib for legacy, structlog for structured events). The `_logger` convention signals "private to module."
