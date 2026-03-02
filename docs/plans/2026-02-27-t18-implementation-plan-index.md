# T18: Extract Orchestrator Phase Methods — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decompose `_execute_run()` (830 lines) and `_process_single_token()` (400 lines) into independently readable, testable methods via pure extract-method refactoring — no behavioral changes.

**Architecture:** Method extraction on existing `Orchestrator` and `RowProcessor` classes. New frozen dataclasses for return types and parameter bundling in `engine/orchestrator/types.py`. Discriminated union types (private) in `processor.py` for transform/gate outcomes. 15 commits, each independently testable.

**Tech Stack:** Python dataclasses (frozen + MappingProxyType), TypeAlias, isinstance-based discriminated unions.

**Design Document:** `docs/plans/2026-02-27-t18-orchestrator-decomposition-design.md` — the authoritative specification. This plan implements that design step-by-step.

---

## Sub-Plans

This implementation is split into three sub-plans by natural boundaries:

| Sub-Plan | File | Commits | Scope |
|----------|------|---------|-------|
| [Part A](2026-02-27-t18-part-a-types-and-tests.md) | Types + Characterization Tests | #0–#2 | Characterization test suite, type definitions, processor outcome types |
| [Part B](2026-02-27-t18-part-b-orchestrator-extractions.md) | Orchestrator Extractions | #3–#10 | All 7 method extractions from `core.py`, main/resume collapse |
| [Part C](2026-02-27-t18-part-c-processor-extractions.md) | Processor Extractions | #11–#14 | All 3 method extractions from `processor.py`, collapse |

## Execution Order

Parts must be executed **in order** (A → B → C). Each part's commits depend on the previous part's types and tests.

## Verification Command (run after every commit)

```bash
.venv/bin/python -m pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ tests/property/engine/ -x --tb=short
```

For high-risk commits (#6, #8, #10, #12), also run:
```bash
.venv/bin/python -m pytest tests/integration/pipeline/ -x --tb=short
```

Full suite for final commit (#14):
```bash
.venv/bin/python -m pytest tests/ -x --tb=short && .venv/bin/python -m mypy src/ && .venv/bin/python -m ruff check src/
```

## Success Criteria

- All 8,000+ tests pass after every commit
- mypy clean
- ruff clean
- No method exceeds 150 lines in final state
- `_execute_run()` → ~90 lines of orchestration
- `_process_single_token()` → ~65 lines of flow control
- `_process_resumed_rows()` shares `LoopContext` and `_flush_and_write_sinks()` with main path
- Characterization test (commit #0) passes after every subsequent commit

## Risk Ranking

| Rank | Commit | Risk | Sub-Plan |
|------|--------|------|----------|
| 1 | #8: `_run_main_processing_loop()` | Highest | Part B |
| 2 | #10: Collapse main+resume | High | Part B |
| 3 | #6: `_handle_quarantine_row()` | Medium-high | Part B |
| 4 | #12: `_handle_gate_node()` | Medium-high | Part C |
| 5 | All others | Lower | Various |
