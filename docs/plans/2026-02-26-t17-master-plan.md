# T17: PluginContext Protocol Split — Master Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decompose the 20-field PluginContext god-object into 4 phase-based protocols (SourceContext, TransformContext, SinkContext, LifecycleContext), enforcing interface segregation across all plugins.

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
```

## Key Design Constraints

1. **Concrete `PluginContext` stays** — executors mutate it between steps
2. **`record_call()` implementation stays on concrete class** — protocols expose the method signature only
3. **`on_start()` receives `LifecycleContext`** (wider), `process()`/`write()`/`load()` receive narrower phase context
4. **Executors keep accepting `PluginContext`** (concrete) — they write to it
5. **Tests mostly don't change** — `PluginContext(...)` constructions still work

## Files Touched (Summary)

| Category | Files | Key Locations |
|----------|-------|---------------|
| Protocol definitions | 1 new | `src/elspeth/contracts/contexts.py` |
| PluginContext cleanup | 1 | `src/elspeth/contracts/plugin_context.py` |
| Plugin protocols | 1 | `src/elspeth/plugins/protocols.py` |
| Base classes | 1 | `src/elspeth/plugins/base.py` |
| Source plugins | 4 | `csv_source.py`, `json_source.py`, `null_source.py`, `blob_source.py` |
| Simple transforms | 5 | `passthrough.py`, `field_mapper.py`, `truncate.py`, `json_explode.py`, `keyword_filter.py` |
| Complex transforms | 3 | `web_scrape.py`, `prompt_shield.py`, `content_safety.py` |
| LLM transforms | 3 | `transform.py`, `openrouter_batch.py`, `azure_batch.py` |
| Sinks | 4 | `csv_sink.py`, `json_sink.py`, `database_sink.py`, `blob_sink.py` |
| Batching | 1 | `batching/mixin.py` |
| Executors | 5 | `transform.py`, `sink.py`, `gate.py`, `aggregation.py`, `state_guard.py` |
| Orchestrator | 3 | `core.py`, `aggregation.py`, `export.py` |
| Operations | 1 | `core/operations.py` |
| Tests | ~70 | Mostly signature changes in test helpers |
| Alignment tests | 1 new | `tests/unit/contracts/test_context_protocols.py` |
