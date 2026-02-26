# T17: PluginContext Protocol Split — Master Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decompose the 19-field PluginContext god-object into 4 phase-based protocols (SourceContext, TransformContext, SinkContext, LifecycleContext), enforcing interface segregation across all plugins.

**Architecture:** Phase-based protocol split — each protocol captures what one plugin category actually accesses. The concrete `PluginContext` class remains as the mutable implementation satisfying all protocols. Executors keep accepting the concrete type (they mutate fields); plugins narrow their signatures to protocol types.

**Tech Stack:** Python `typing.Protocol` with `@runtime_checkable`, mypy strict mode for structural verification, existing `test_config_alignment.py` pattern for protocol alignment tests.

---

## Sub-Plans

This work is split into 5 self-contained sub-plans, each executable in a separate session:

| Sub-Plan | File | Phases | Effort | Risk |
|----------|------|--------|--------|------|
| **Phase 0: Cleanup** | `2026-02-26-t17-phase0-cleanup.md` | Remove dead fields | S | Low |
| **Phase 1: Protocols** | `2026-02-26-t17-phase1-protocols.md` | Define protocols + alignment tests | M | Med |
| **Phase 2-3: Signatures & Plugins** | `2026-02-26-t17-phase2-3-signatures-plugins.md` | Update all plugin signatures | L | Med-High |
| **Phase 4: Engine** | `2026-02-26-t17-phase4-engine.md` | Update executors + orchestrator | M | High |
| **Finishing** | `2026-02-26-t17-finishing.md` | Test updates + verification gate | L | Low |

## Execution Order & Dependencies

```text
Phase 0 ──→ Phase 1 ──→ Phase 2-3 ──→ Phase 4 ──→ Finishing
(cleanup)   (protocols)  (plugins)     (engine)    (tests+gate)
```

Each phase is a **commit boundary** — tests must pass at the end of each phase. Phase 2-3 combines signature updates with plugin updates because they must be done together for mypy to pass.

## Quality Gates (per-phase)

Every phase must pass ALL of these before proceeding:
```bash
.venv/bin/python -m pytest tests/ -x --timeout=120    # All tests pass
.venv/bin/python -m mypy src/                          # Type checking clean
.venv/bin/python -m ruff check src/                    # Linting clean
.venv/bin/python -m scripts.check_contracts            # Config contracts pass
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model  # Tier model clean
```

## Key Design Constraints

1. **Concrete `PluginContext` stays** — executors mutate it between steps
2. **`record_call()` implementation stays on concrete class** — protocols expose the method signature only
3. **`on_start()`/`on_complete()` receive `LifecycleContext`** (wider), `process()`/`write()`/`load()` receive narrower phase context
4. **Executors keep accepting `PluginContext`** (concrete) — they write to it
5. **Tests mostly don't change** — ~444 direct `PluginContext(...)` constructions across ~69 test files continue to work because the concrete class satisfies all 4 protocols. **Exception [B1]:** contract test base fixtures that pass `plugin_name="test"` must be updated in Phase 0 when the field is removed

## Files Touched (Summary)

| Category | Files | Key Locations |
|----------|-------|---------------|
| Protocol definitions | 1 new | `src/elspeth/contracts/contexts.py` |
| PluginContext cleanup | 1 | `src/elspeth/contracts/plugin_context.py` |
| Plugin protocols | 1 | `src/elspeth/plugins/protocols.py` |
| Base classes | 1 | `src/elspeth/plugins/base.py` |
| Source plugins | 4 | `csv_source.py`, `json_source.py`, `null_source.py`, `blob_source.py` |
| Simple transforms | 7 | `passthrough.py`, `field_mapper.py`, `truncate.py`, `json_explode.py`, `keyword_filter.py`, `batch_stats.py`, `batch_replicate.py` |
| Complex transforms | 3 | `web_scrape.py`, `prompt_shield.py`, `content_safety.py` |
| LLM transforms | 3 | `transform.py`, `openrouter_batch.py`, `azure_batch.py` |
| Sinks | 4 | `csv_sink.py`, `json_sink.py`, `database_sink.py`, `blob_sink.py` |
| Batching | 1 | `batching/mixin.py` |
| Executors | 5 | `transform.py`, `sink.py`, `gate.py`, `aggregation.py`, `state_guard.py` |
| Orchestrator | 4 | `core.py`, `aggregation.py`, `export.py`, `outcomes.py` |
| Processor | 1 | `engine/processor.py` |
| Operations | 1 | `core/operations.py` |
| Tests | ~70 | Mostly signature changes in test helpers |
| Alignment tests | 1 new | `tests/unit/contracts/test_context_protocols.py` |

## Review Findings (2026-02-26)

4-agent review panel (Architecture Critic, Systems Thinker, Quality Analyst, Reality Checker) reviewed all sub-plans against the actual codebase. Amendments have been applied inline to each sub-plan.

### Blocking (fixed in plan)

| ID | Finding | Source | Fix Location |
|----|---------|--------|--------------|
| B1 | `plugin_name="test"` in contract test base fixtures breaks after Phase 0 | Quality | Phase 0, Task 1 |

### High-Priority Warnings (addressed in plan)

| ID | Finding | Source | Fix Location |
|----|---------|--------|--------------|
| W1 | Defensive fallback removal may break tests that skip `on_start()` | Systems + Quality | Phase 2-3, Task 5 |
| W2 | `blob_sink._resolve_display_headers_if_needed` missing from helper list | Systems | Phase 2-3, Task 7 |
| W3 | Phase 2-3 has no sub-checkpoint within 19 plugin files | Systems | Phase 2-3, Task 4a |

### Medium-Priority Recommendations (addressed in plan)

| ID | Finding | Source | Fix Location |
|----|---------|--------|--------------|
| R1 | Add `node_id` to `LifecycleContext` | Architecture | Phase 1, Task 1 |
| R2 | Strengthen negative discrimination tests with real minimal objects | Architecture + Quality | Phase 1, Task 3 |
| R3 | Use mechanical introspection instead of hardcoded field lists | Quality | Phase 1, Task 4 |
| R4 | Document `record_transform_error()` exclusion from protocols | Systems + Architecture | Phase 1, Task 1 |
| R5 | Prefer exact signature match over `**kwargs` for test subclass fixes | Quality | Finishing, Task 2 |
| R6 | `payload_store` not wired in orchestrator (pre-existing) | Reality | Phase 2-3, Task 5 |

### Informational Notes (documented in plan)

| ID | Finding | Source | Location |
|----|---------|--------|----------|
| N1 | `@property` in Protocol vs plain dataclass fields — works correctly | Architecture + Reality | Phase 1, Task 2 |
| N2 | `from __future__ import annotations` + `@runtime_checkable` — no interaction issues | Reality | Phase 1, Task 1 |
| N3 | `web_scrape` refactor moves crash from row-time to start-time (strictly better) | Architecture + Systems | Phase 2-3, Task 5 |
| N4 | `record_call()` crosses protocol boundaries internally — correct (impl on concrete class) | Architecture | Design doc |
| N5 | `SinkContext` correctly omits `telemetry_emit` (accessed via `self` in `record_call()`) | Architecture | Design doc |
| N6 | All 40+ line numbers verified accurate by Reality Checker (0 hallucinations) | Reality | All phases |
| N7 | `isinstance()` only checks attribute names, not signatures — mypy is the real guard | Architecture + Quality | Phase 1, Task 2 |
| N8 | `LLMQueryStrategy` protocol line numbers unverified (low risk) | Reality | Phase 2-3, Task 6 |
| N9 | Four source plugin line numbers unverified (low risk, edit guidance only) | Reality | Phase 2-3, Task 3 |
| N10 | Partial completion after any phase is safe; mid-Phase 2-3 is highest stall risk | Systems | Phase 2-3 |
