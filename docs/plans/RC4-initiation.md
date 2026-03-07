# RC4 Initiation Plan

**Date:** 2026-03-07
**Branch:** RC4-user-interface
**Lineage:** Plan audit of `docs/plans/` — consolidation of unimplemented work from RC2/RC3 era plans

---

## Context

An audit of 38 plan files in `docs/plans/` on 2026-03-07 found 28 fully implemented plans that were removed (preserved in git history). This document consolidates the surviving unimplemented work into a single RC4 scope, organized by priority tier.

### RC3 Remediation Status Update

The RC3 remediation plan (`RC3-remediation.md`) listed 10 remaining items. The audit found:

| Item | Status | Notes |
|------|--------|-------|
| CRIT-02 | **Mostly done** | `or {}` patterns replaced with `TokenUsage.from_dict(data.get("usage"))`. Remaining `.get("usage")` is correct Tier 3 boundary access. Consider closing. |
| FEAT-04 | Open | Missing CLI commands: `status`, `export`, `db migrate` |
| FEAT-05 | Done | Graceful shutdown implemented |
| FEAT-06 | Open | Circuit breaker for retry logic |
| ARCH-06 | **Done** | `_AggregationNodeState` consolidation completed (old dict names appear only in comment at line 125) |
| ARCH-14 | Open | Resume schema verification gap |
| ARCH-15 | Open | Per-branch fork transforms (separate design doc) |
| QW-10 | Open | CLI event formatter extraction |
| DOC-01/02 | Done | Example READMEs created |
| OBS-04 | Open | Prometheus metrics integration |

### Field Collision Prevention Status Update

The field collision design (`2026-02-15-field-collision-prevention-design.md`) described per-plugin wiring of `detect_field_collisions()`. The actual implementation took a better path:

- **Engine-level enforcement** at `engine/executors/transform.py:212-229` — centralized, mandatory, pre-execution
- All transforms (LLM, web_scrape, json_explode, batch_replicate) declare `declared_output_fields`
- Config-time validators in `json_explode` and `web_scrape` reject self-collisions
- `PluginContractViolation` raised on collision — row never processed

**Assessment:** Field collision prevention is complete. Both plan files can be retired.

---

## RC4 Scope

### Phase 1: Correctness (P1 — do first)

These items prevent silent data corruption or ensure crash recovery integrity.

#### 1.1 Resume Schema Verification (from ARCH-14)

**Problem:** `core/checkpoint/recovery.py` cannot verify that the source schema matches the original run's schema. A schema change between runs silently corrupts data.

**Fix:** Record schema fingerprint (canonical hash of field names + types) in checkpoint metadata. On resume, compare and fail fast on mismatch.

**Existing plan:** `RC3-remediation.md` §ARCH-14

---

#### 1.2 Per-Branch Fork Transforms (from ARCH-15)

**Problem:** Fork/coalesce is merge-barrier-only — cannot run different processing per branch. Three architectural barriers (builder connection bypass, runtime coalesce jump, topological map invisibility).

**Fix:** Comprehensive design reviewed by 4 SME agents. Allow branch names as consumable connections; use token branch identity for coalesce correlation.

**Existing plan:** `ARCH-15-design.md` (530 lines, ready for implementation)
**Filigree:** `elspeth-rapid-jyvr`

---

### Phase 2: Type Safety (P2 — high value, schedule deliberately)

#### 2.1 NodeInfo Typed Config (from `2026-02-01-nodeinfo-typed-config.md`)

**Problem:** `NodeInfo.config` is `dict[str, Any]` (`core/dag/models.py:80`). Gate, aggregation, and coalesce configs are framework-synthesized and fully known, yet accessed via untyped dict lookups — a Tier 1 violation of offensive programming principles.

**Fix:** Discriminated union of frozen dataclasses (`GateNodeConfig`, `AggregationNodeConfig`, `CoalesceNodeConfig`) with opaque wrapper for plugin configs. Typed accessors replace `config["schema"]` patterns.

**Blast radius:** Every executor, DAG builder, and graph construction site. Big refactor — best scheduled before Engine API extraction (`elspeth-1119dc22ef`) where it prevents integration bugs in the new API surface.

**Existing plan:** `2026-02-01-nodeinfo-typed-config.md`

---

#### 2.2 Tier Model Whitelist Reduction (from `2026-02-02-whitelist-reduction.md`)

**Problem:** 547 entries in enforcement whitelist, 488 expiring on **2026-05-02**. Only Phase 1.1 done (19 entries removed). Boilerplate justifications suggest rubber-stamp approval.

**Options:**
1. **Grind through reductions** — 4 phases, hundreds of entries, multiple sessions
2. **Extend expiry dates** — buys time but defers the work
3. **Hybrid** — extend dates for legitimate patterns (R5 isinstance ~250), grind through likely-bug-hiding patterns (R1 .get ~167, R9 .pop ~11, R3 hasattr ~9)

**Recommendation:** Option 3. The R5 isinstance entries are mostly legitimate AST/type work — extend those permanently with proper justifications. Focus grind sessions on R1/R2/R3/R7/R9 patterns (~196 entries) where `.get()` on internal state hides real bugs.

**Existing plan:** `2026-02-02-whitelist-reduction.md`
**Deadline:** 2026-05-02 (expiry cliff)

---

### Phase 3: Platform Completeness (P2 — operational gaps)

#### 3.1 Missing CLI Commands (from FEAT-04)

- `elspeth status` — run status summary
- `elspeth export` — CLI surface for landscape exporter
- `elspeth db migrate` — Alembic migration command

**Existing plan:** `RC3-remediation.md` §FEAT-04

---

#### 3.2 Circuit Breaker for Retry Logic (from FEAT-06)

**Problem:** 10,000 rows against a dead service = hours of retries. No fast-fail after consecutive failures.

**Fix:** After N consecutive failures to same endpoint, fail fast for M seconds. Integrate with existing `RetryManager` + tenacity.

**Existing plan:** `RC3-remediation.md` §FEAT-06

---

### Phase 4: Code Quality (P3 — nice to have)

#### 4.1 Contract Propagation Complex Fields

**Problem:** `dict`/`list` output fields from transforms silently dropped during contract propagation. Small fix: change `TypeError` path from "skip" to "infer as `object`".

**Existing plan:** `2026-02-13-contract-propagation-complex-fields.md`

---

#### 4.2 CLI Event Formatter Extraction (from QW-10)

**Problem:** Event handling in `cli.py` is monolithic. Extract shared formatting to helper module.

**Existing plan:** `RC3-remediation.md` §QW-10

---

#### 4.3 Prometheus Metrics Integration (from OBS-04)

**Problem:** Telemetry covers tracing and event streaming but no pull metrics for operational dashboards.

**Existing plan:** `RC3-remediation.md` §OBS-04

---

### Future: LLM Plugin Consolidation

Approved design exists (`2026-02-25-llm-plugin-consolidation.md`) to collapse 6 LLM transform classes into Strategy pattern with `LLMProvider` protocol. Quality assessment (`05-quality-assessment-t10-llm-consolidation.md`) identified 2 HIGH-priority findings.

**Not scheduled for RC4.** The old implementation plan (`2026-02-25-llm-plugin-consolidation-impl.md`) was deleted as stale — file paths moved during plugins restructure and T17 protocol split. A fresh implementation plan should be written against the current codebase when this work is scheduled.

---

## Dependency Map

```
Phase 1 (Correctness)
├── 1.1 Resume Schema Verification (independent)
└── 1.2 Per-Branch Fork Transforms (independent, largest item)

Phase 2 (Type Safety)
├── 2.1 NodeInfo Typed Config (schedule before Engine API extraction)
└── 2.2 Whitelist Reduction (deadline: 2026-05-02)

Phase 3 (Platform Completeness)
├── 3.1 CLI Commands (independent)
└── 3.2 Circuit Breaker (independent)

Phase 4 (Code Quality) — all independent, do opportunistically
├── 4.1 Contract Propagation
├── 4.2 CLI Formatter Extraction
└── 4.3 Prometheus Metrics
```

No hard dependencies between phases. Phase 2.1 should precede Engine API extraction work on the critical path.

---

## Plans to Retire After This Document

These plans are now subsumed by this RC4 initiation plan:

| Plan | Reason |
|------|--------|
| `RC3-remediation.md` | Remaining items absorbed into Phases 1-4. ARCH-06 and CRIT-02 confirmed done. |
| `2026-02-15-field-collision-prevention-design.md` | Confirmed fully implemented via engine-level enforcement |
| `2026-02-15-field-collision-prevention.md` | Confirmed fully implemented via engine-level enforcement |

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-07 | 1.0 | Initial RC4 scope from plan audit |
