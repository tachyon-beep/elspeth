# Engine Orchestrator Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/engine-orchestrator/` (8 findings from static analysis)
**Source code reviewed:** `core.py`, `outcomes.py`, `aggregation.py`, `export.py`, `types.py`

## Summary

| # | Bug | Original | Triaged | Verdict |
|---|-----|----------|---------|---------|
| 1 | accumulate_row_outcomes unrecognized | P1 | **closed** | False positive — StrEnum; all 9 values handled |
| 2 | check_aggregation_timeouts no checkpoint | P1 | **P2 downgrade** | Real gap but narrow crash window; next row covers |
| 3 | coalesce timeout/flush invalid CoalesceOutcome | P1 | **P3 downgrade** | Requires CoalesceExecutor bug; defense-in-depth |
| 4 | plugin cleanup skipped after on_start | P1 | **P1 confirmed** | Real resource leak; on_start before try/finally |
| 5 | reconstruct_schema_from_json Optional[Decimal] | P1 | **P1 confirmed** | 3-branch anyOf falls through; resume crashes |
| 6 | resume leaves run in RUNNING | P1 | **P1 confirmed** | No except Exception; run becomes unrecoverable |
| 7 | AggregationFlushResult mutable dict | P2 | **P2 confirmed** | No current mutation but violates frozen contract |
| 8 | resume telemetry flush missing | P2 | **P2 confirmed** | Asymmetry with run(); events may be lost |

## Detailed Assessment

### 1. accumulate_row_outcomes unrecognized — CLOSED (false positive)

`RowOutcome` is a Python `StrEnum` with exactly 9 members. All 9 are handled in the if/elif chain
at lines 72-119. `StrEnum` prevents construction of non-member values at runtime. An `else` clause
would be dead code. Static analysis tool did not model enum exhaustiveness.

### 2. check_aggregation_timeouts no checkpoint — DOWNGRADED to P2

The asymmetry is real: `flush_remaining_aggregation_buffers()` supports `checkpoint_callback` but
`check_aggregation_timeouts()` does not. However, the next processed row creates a progressive
checkpoint covering the flushed work, so the crash window is narrow (between timeout flush and
next row's checkpoint).

### 3. coalesce timeout/flush invalid CoalesceOutcome — DOWNGRADED to P3

The theoretical gap (merged_token=None AND failure_reason=None AND held=False) requires
CoalesceExecutor to produce a malformed outcome. Since the executor is system-owned code, this
would indicate a separate bug. An `else: raise OrchestrationInvariantError(...)` guard would be
defense-in-depth.

### 4. plugin cleanup skipped — CONFIRMED P1

`on_start()` is called at lines 1216-1220 (run) and 2146-2149 (resume), but the try/finally that
calls `_cleanup_plugins` starts later at lines 1286 (run) and 2182 (resume). If `_build_processor()`
fails between those points, started plugins never get cleaned up. This violates the lifecycle
contract and leaks resources (DB connections, file handles, thread pools).

### 5. reconstruct_schema_from_json Optional[Decimal] — CONFIRMED P1

`_json_schema_to_python_type` handles Decimal (anyOf[number,string] without null) and nullable
(anyOf[T,null] with exactly one non-null branch) as separate patterns. Optional[Decimal] produces
a 3-branch anyOf[number,string,null] that matches neither pattern and falls through to ValueError.
Resume crashes for any source with nullable Decimal fields.

### 6. resume leaves run in RUNNING — CONFIRMED P1

`resume()` sets `RunStatus.RUNNING` then only handles `GracefulShutdownError`. Any other exception
(RuntimeError, OrchestrationInvariantError, DB error) leaves the run in RUNNING permanently.
Recovery then rejects RUNNING as "still in progress" (recovery.py:100-101), making the run
unrecoverable. Compare with `run()` which has `except Exception` → `RunStatus.FAILED`.

### 7. AggregationFlushResult mutable dict — CONFIRMED P2

`frozen=True` on the dataclass blocks attribute reassignment but not in-place mutation of the
`dict`. No current code mutates after construction, but `MappingProxyType` is the established
pattern (from Routing Trilogy) and should be applied for consistency.

### 8. resume telemetry flush — CONFIRMED P2

`run()` has a finally block at lines 952-976 calling `_flush_telemetry()`. `resume()` has no
equivalent. Telemetry events emitted during resume may be lost, and
`fail_on_total_exporter_failure` is bypassed.

## Cross-Cutting Observations

1. **resume() is consistently under-specified vs run().** Bugs 6 and 8 both stem from features
   in run() not mirrored in resume(). A structural parity audit of resume() vs run() would catch
   the entire class.

2. **Schema reconstruction is compositional but doesn't compose.** Bug 5 shows that combining
   two individually-supported patterns (Decimal anyOf + nullable anyOf) creates a compound
   pattern that the code doesn't recognize. Fix: check for Decimal pattern within nullable handling.

3. **Static analysis consistently over-classifies enum exhaustiveness.** Bug 1 is a false
   positive because Python StrEnum provides runtime exhaustiveness guarantees that static
   analysis tools don't model.
