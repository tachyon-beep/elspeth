# ELSPETH RC-3 Remediation Plan

**Date:** 2026-02-13
**Lineage:** Remaining items from RC-2 Comprehensive Remediation Plan (2026-01-27)
**Source:** Architecture Analysis by 17+ parallel agents (archive/2026-01-27-arch-analysis/)
**Original Issues:** 75+ | **Resolved Piecemeal:** ~57 | **Remaining:** 18

---

## Context

The RC-2 remediation plan identified 75+ issues across 6 phases. Over the course of the
RC2.x bug sprints, routing trilogy, test suite v2 migration, telemetry implementation,
and RC3-quality-sprint, approximately 57 items were resolved piecemeal. This plan
captures only the items that remain unaddressed.

### What Was Completed (not repeated here)

**Phase 0 Quick Wins:** 11/12 done (QW-01 through QW-09, QW-11, QW-12)
**Phase 1 Critical Fixes:** 3/4 done (CRIT-01 rate limiting, CRIT-03 coalesce timeout, CRIT-04 HTTP JSON parse)
**Phase 2 Core Features:** 3/6 done (FEAT-01 explain command, FEAT-02 TUI widgets, FEAT-03 checkpoints)
**Phase 3 Production Hardening:** 11/12 done (all PERF items, SAFE-01/02/03/04/06/07/08)
**Phase 4 Architecture:** 12/18 done (ARCH-03/04/05/08/09/10/11/12/15/16/17/18)
**Phase 5 Quality:** 7+ done (TEST-02/03/04, OBS-01/02/03, SEC-01)
**N/A by design:** ARCH-01 BaseCoalesce, ARCH-08 gate discovery (gate plugins removed entirely)

---

## Remaining Phase 1: LLM Boundary Validation

### CRIT-02: Replace `.get()` Chains on External API Responses
**Source:** TD-002 | **Priority:** MEDIUM (downgraded — partial progress made)

LLM plugins partially cleaned up, but `.get()` chains on external API response structures
may persist in some files. These are at Tier 3 boundaries (external data), so the risk is
lower than originally assessed — the pattern is technically correct (defensive on external
data) but produces silent empty-dict fallbacks instead of actionable error messages.

**Files to audit:**
- `src/elspeth/plugins/llm/azure_multi_query.py`
- `src/elspeth/plugins/llm/openrouter.py`
- `src/elspeth/plugins/llm/openrouter_multi_query.py`
- `src/elspeth/plugins/llm/openrouter_batch.py`

**Fix:** Replace `.get("key", {})` chains with explicit key checks that return
`TransformResult.error()` with diagnostic info on unexpected response shapes.

---

## Remaining Phase 2: Feature Gaps

### FEAT-04: Add Missing CLI Commands
**Source:** TD-027 | **Priority:** MEDIUM

Current CLI has: `run`, `explain`, `validate`, `plugins list`, `purge`, `resume`, `health`.

**Missing:**
- `elspeth status` — show run status summary
- `elspeth export` — export audit trail (landscape exporter exists but no CLI surface)
- `elspeth db migrate` — run Alembic migrations (Alembic configured but no CLI command)

---

### FEAT-05: Add Graceful Shutdown
**Source:** TD-017 | **Priority:** HIGH

No signal handlers (SIGTERM, SIGINT) in orchestrator. Long-running pipelines cannot be
stopped cleanly.

**Implementation:**
- Add signal handlers in orchestrator startup
- On signal: create checkpoint, flush pending aggregations, complete in-flight writes
- Set run status to INTERRUPTED (not FAILED)

---

### FEAT-06: Add Circuit Breaker to Retry Logic
**Source:** Discovery Findings | **Priority:** MEDIUM

RetryManager uses tenacity exponential backoff but no circuit breaker. 10,000 rows against
a dead service = hours of retries before all rows fail.

**Fix:** After N consecutive failures to same endpoint, fail fast for M seconds.

---

## Remaining Phase 3: Production Hardening

### SAFE-05: Fix Call Index Counter Persistence
**Source:** TD-018 | **Priority:** LOW

`_call_indices` and `_operation_call_indices` in recorder are in-memory dicts. On recorder
recreation (resume), counters reset to 0, risking call_index collisions.

**Fix:** Query MAX(call_index) from database on recorder init, or include run_id+node_id
in the uniqueness constraint.

---

## Remaining Phase 4: Architecture Cleanup

### ARCH-02: Clarify LLM Transform Execution Model
**Source:** TD-013 | **Priority:** LOW

LLM transforms use `accept()` for streaming batch processing rather than `process()`.
The inheritance relationship with `BaseTransform` may create confusion about which
method to call. Verify current state and document the execution model clearly.

---

### ARCH-06: Consolidate AggregationExecutor Parallel Dictionaries
**Source:** Engine Analysis | **Priority:** MEDIUM

`engine/executors/aggregation.py` maintains 6 parallel dictionaries (`_buffers`,
`_buffer_tokens`, `_batch_ids`, `_member_counts`, `_trigger_evaluators`,
`_restored_states`) that must stay synchronized.

**Fix:** Consolidate into a single `AggregationNodeState` dataclass keyed by node_id.

---

### ARCH-07: Document Lifecycle Hook Contract
**Source:** Plugin Analysis | **Priority:** LOW

`on_start()`/`on_complete()` ordering undefined. `close()` vs `on_complete()` semantics
overlap. Document the lifecycle contract clearly in plugin base classes.

---

### ARCH-13: Clean Up Repository Session Parameter
**Source:** TD-022 | **Priority:** LOW

All repositories receive `None` for session and never use it. Remove the parameter or
implement proper session passing.

---

### ARCH-14: Fix Resume Schema Verification Gap
**Source:** Core Analysis | **Priority:** MEDIUM

`core/checkpoint/recovery.py` requires `source_schema_class` but cannot verify it matches
the original run's schema. A schema change between runs could silently corrupt data.

---

## Remaining Phase 5: Quality & Documentation

### QW-10: Extract CLI Event Formatters
**Source:** TD-014 | **Priority:** LOW

Event handling logic in `cli.py` (~2,000 lines) is monolithic. Extract shared event
formatting to a helper module to reduce duplication.

---

### TEST-01: Reduce Test Path Integrity Violations
**Source:** TD-015 | **Priority:** LOW (downgraded)

~62 instances of `graph._` private access in tests. Per CLAUDE.md, private access in
unit tests of isolated algorithms (topo sort, cycle detection) is acceptable. Audit
remaining instances to confirm they're all in that category.

---

### DOC-01: Add Missing Example READMEs
**Source:** Examples Analysis | **Priority:** LOW

Directories missing READMEs: `batch_aggregation`, `boolean_routing`, `deaggregation`,
`json_explode`, `threshold_gate`, `threshold_gate_container`.

---

### DOC-02: Add Fork/Coalesce Examples
**Source:** Examples Analysis | **Priority:** LOW

No working examples demonstrating fork/join DAG patterns.

---

### DOC-03: Document Access Control Limitations
**Source:** Security Analysis | **Priority:** LOW

Add note: "ELSPETH is not multi-user. Assumes single-user or fully trusted network."

---

### DOC-04: Document Checkpoint Breaking Change
**Source:** Schema Evolution Analysis | **Priority:** LOW

All checkpoints before 2026-01-24 are invalid due to node ID changes.

---

### DOC-05: Document Audit Export Signing
**Source:** Security Analysis | **Priority:** LOW

Document: Enable `landscape.export.sign = true` for legal-grade integrity.

---

### OBS-04: Add Metrics/Prometheus Integration
**Source:** Observability Analysis | **Priority:** LOW

Telemetry subsystem covers tracing and event streaming. No Prometheus-style pull metrics
for operational dashboards (request rates, error rates, processing latency histograms).

---

## Effort Summary

| Category | Items | Estimated Effort |
|----------|-------|------------------|
| Feature Gaps (FEAT-04/05/06) | 3 | 8-15 days |
| LLM Boundary Validation (CRIT-02) | 1 | 1-2 days |
| Production Hardening (SAFE-05) | 1 | 1-2 days |
| Architecture (ARCH-02/06/07/13/14) | 5 | 5-10 days |
| Quality/Docs (QW-10, TEST-01, DOC-*, OBS-04) | 8 | 5-10 days |
| **Total** | **18** | **~20-40 days** |

---

## Priority Ordering for RC-3

**Must-have for RC-3 release:**
1. FEAT-05: Graceful shutdown (data loss risk without it)

**Should-have:**
2. FEAT-04: CLI surface for export/status/migrate
3. ARCH-06: AggregationExecutor state consolidation
4. ARCH-14: Resume schema verification
5. CRIT-02: LLM boundary validation audit

**Nice-to-have:**
6. Everything else (LOW priority, quality-of-life improvements)

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-27 | 1.0 | Initial RC-2 plan from 17+ agent analysis (75+ items) |
| 2026-02-13 | 2.0 | Rebaselined for RC-3: removed ~57 completed items, 18 remain |
