# Analysis: src/elspeth/engine/orchestrator/core.py

**Lines:** 2,319
**Role:** The Orchestrator -- manages the full lifecycle of a pipeline run. Handles phase transitions (DATABASE -> GRAPH -> SOURCE -> PROCESS -> EXPORT -> DONE/FAILED), coordinates source loading, row processing dispatch, sink finalization, checkpoint creation, telemetry emission, and error handling. This is the "main loop" of the engine. It also implements `resume()` for crash recovery from checkpoints.
**Key dependencies:**
- Imports from: `LandscapeDB`, `LandscapeRecorder`, `ExecutionGraph`, `RowProcessor`, `RetryManager`, `SpanFactory`, `PluginContext`, `SinkExecutor`, `CoalesceExecutor`, `TokenManager`, `CheckpointManager`, `RecoveryManager`, `track_operation`, orchestrator submodules (`validation.py`, `export.py`, `aggregation.py`, `types.py`)
- Imported by: `elspeth.engine.orchestrator.__init__` (re-exported as public API), CLI layer
- Delegates to: `validation.py` (route validation), `export.py` (landscape export + schema reconstruction), `aggregation.py` (timeout/flush handling)
**Analysis depth:** FULL

## Summary

The Orchestrator is a well-structured state machine with careful attention to audit integrity, exception handling, and the deferred-outcome pattern (recording outcomes only after sink durability). The code is heavily documented with inline rationale comments. However, there are several concrete bugs: missing counter increments in the resume path that cause incorrect `RunResult` metrics, double-close of transforms due to overlapping finally blocks, and massive code duplication between the main run and resume paths (~800 lines of near-identical outcome-handling logic) that has already caused divergence bugs. The file is maintainable but at the boundary of manageable complexity.

## Critical Findings

### [2120] Missing `rows_succeeded` increment in resume coalesce-timeout path

**What:** In `_process_resumed_rows()`, when processing coalesce timeouts (lines 2098-2141), the handler for `RowOutcome.COMPLETED` at line 2120 does NOT increment `rows_succeeded`. The equivalent code in the main run path at line 1305 DOES increment it.

**Why it matters:** The `RunResult.rows_succeeded` counter will be under-counted for resumed runs that involve coalesce timeouts with downstream processing. This causes incorrect metrics reported to the CLI, the `RunSummary` event, and any monitoring/alerting. For an audit system, incorrect metrics undermine operational trust -- operators cannot accurately assess how many rows were successfully processed during recovery.

**Evidence:**
Main run path (correct):
```python
# Line 1304-1305
if cont_result.outcome == RowOutcome.COMPLETED:
    rows_succeeded += 1  # <-- present
    sink_name = default_sink_name
```

Resume path (missing):
```python
# Line 2120-2121
if cont_result.outcome == RowOutcome.COMPLETED:
    # rows_succeeded += 1  <-- MISSING
    sink_name = default_sink_name
```

### [2135-2139] Missing `rows_succeeded` increment in resume coalesce-timeout terminal path

**What:** In `_process_resumed_rows()`, when a coalesce timeout produces a merged token with no downstream nodes (line 2135 else branch), the token is added to `pending_tokens` but `rows_succeeded` is NOT incremented. The equivalent code in the main run path at line 1331 DOES increment it.

**Why it matters:** Same impact as the previous finding -- `rows_succeeded` will be under-counted. The combination of both missing increments means that ALL coalesced rows during resume are excluded from the success count, potentially making a successful resume appear to have produced far fewer results than it actually did.

**Evidence:**
Main run path (correct):
```python
# Line 1327-1333
else:
    # No downstream nodes - send directly to sink
    rows_succeeded += 1  # <-- present
    pending_tokens[default_sink_name].append(...)
```

Resume path (missing):
```python
# Line 2135-2139
else:
    # No downstream nodes - send directly to sink
    # rows_succeeded += 1  <-- MISSING
    pending_tokens[default_sink_name].append(...)
```

### [635 + 1613-1638] Double-close of transforms on normal run path

**What:** `_execute_run()` has a finally block (lines 1592-1644) that calls `transform.on_complete(ctx)` and `transform.close()` for all transforms, `sink.on_complete(ctx)` and `sink.close()` for all sinks, and `source.on_complete(ctx)` and `source.close()` for the source. The outer `run()` method also has a finally block (lines 610-635) that calls `self._cleanup_transforms(config)`, which calls `transform.close()` again for all transforms.

This means on every normal `run()` invocation (whether it succeeds or fails), `transform.close()` is called TWICE: first in `_execute_run`'s finally, then in `run()`'s finally.

**Why it matters:** If any transform's `close()` method is not idempotent (e.g., it closes a file handle, releases a database connection, or calls an API to finalize work), calling it twice could raise an exception on the second call. The second `close()` happens in `_cleanup_transforms()` which collects errors and then raises `RuntimeError`. This would mask the original exception or create confusing cleanup errors. Even if all current plugins have idempotent `close()`, this is a latent bug that will manifest when any plugin with non-trivial cleanup is added.

**Evidence:**
```python
# _execute_run finally block (line 1613 + 2280)
for transform in config.transforms:
    try:
        transform.on_complete(ctx)       # First on_complete call
    except Exception as e: ...
# ... (source/sink close) ...
for transform in config.transforms:
    try:
        transform.close()                # First close() call
    except Exception as e: ...

# run() finally block (line 635)
finally:
    self._cleanup_transforms(config)     # Calls close() AGAIN
```

Note: `_cleanup_transforms` only closes transforms, not sinks/source. But the transforms get double-closed.

## Warnings

### [946-1570 vs 1978-2248] Massive code duplication between run and resume paths

**What:** The outcome-handling logic in `_execute_run()` (lines 1232-1336 for main loop, 1415-1471 for flush_pending) and `_process_resumed_rows()` (lines 2057-2092 for main loop, 2175-2217 for flush_pending) is nearly identical -- approximately 800 lines of duplicated outcome-routing and counter-management code. Both paths also duplicate the coalesce timeout handling, aggregation flushing, sink writing with groupby, and the finally-block cleanup.

**Why it matters:** The `rows_succeeded` counter bugs documented in Critical Findings above are a direct consequence of this duplication. When code was changed in one path, the corresponding change was missed in the other. This duplication creates a maintenance hazard: every future change to outcome handling, counter logic, or sink routing must be made in at least two places (sometimes four, counting the in-loop and end-of-source variants). This is the kind of duplication that leads to progressive divergence and subtle production bugs.

**Evidence:** The missing `rows_succeeded` increments at lines 2120 and 2139 are exactly the divergence pattern this duplication enables.

### [621] Inconsistent `sys.exc_info()` index in `run()` finally block

**What:** The `run()` method's finally block at line 621 reads `pending_exc = sys.exc_info()[0]`, which captures the exception **type** (class). The `_execute_run()` finally at line 1598 and `_process_resumed_rows()` finally at line 2255 both use `sys.exc_info()[1]`, which captures the exception **instance**.

**Why it matters:** At line 631, `pending_exc` is compared to `None` -- this works correctly for both the type and instance (both are non-None when an exception is active). However, the semantics differ: `sys.exc_info()[0]` returns `<class 'RuntimeError'>` while `[1]` returns the actual `RuntimeError("message")` instance. If any code downstream ever needs to inspect the exception details (e.g., for error messages in chaining), the type variant provides less information. More importantly, the inconsistency suggests a copy-paste error and undermines confidence in the exception handling.

**Evidence:**
```python
# Line 621 (run() finally)
pending_exc = sys.exc_info()[0]  # Gets exception TYPE

# Line 1598 (_execute_run() finally)
pending_exc = sys.exc_info()[1]  # Gets exception INSTANCE

# Line 2255 (_process_resumed_rows() finally)
pending_exc = sys.exc_info()[1]  # Gets exception INSTANCE
```

### [1640-1644] Cleanup error in `_execute_run` finally can mask original exception

**What:** When `_execute_run()` fails (an exception is propagating), the finally block collects cleanup errors. At line 1642-1643, if there are cleanup errors AND a pending exception, it raises a new `RuntimeError` with `from pending_exc`. This replaces the original exception's propagation with a new RuntimeError, and the original exception is relegated to the `__cause__` chain.

**Why it matters:** The caller (`run()`) catches `Exception` at line 558. When the cleanup error replaces the original, the `except Exception` block sees a `RuntimeError` about cleanup, not the original processing failure. The original exception is still accessible via `__cause__`, but any logic that inspects the exception type (like the `BatchPendingError` check at line 551) would not match. Specifically: if `_execute_run` raises `BatchPendingError` and then a cleanup hook fails, the `except BatchPendingError` at line 551 would NOT catch it -- the `RuntimeError` from cleanup would propagate to the generic `except Exception` at line 558, causing the run to be marked as FAILED instead of being re-queued for retry.

**Evidence:**
```python
# _execute_run finally block
if cleanup_errors:
    error_summary = "; ".join(cleanup_errors)
    if pending_exc is not None:
        raise RuntimeError(f"Plugin cleanup failed: {error_summary}") from pending_exc
        # ^-- This replaces BatchPendingError with RuntimeError
```

### [580-582] `finalize_run(FAILED)` called in error handler without guarding against double-finalize

**What:** When `run_completed` is False in the `except Exception` handler at line 582, `recorder.finalize_run(run.run_id, status=RunStatus.FAILED)` is called. However, `_execute_run` could have partially completed -- for example, if the method raised after the processing loop but before returning (e.g., during the sink write phase). There is no guard against calling `finalize_run` on a run that was already finalized by some other path.

**Why it matters:** If `finalize_run` is not idempotent (e.g., it does a conditional UPDATE and fails if the run is already in a terminal status), this could raise a secondary exception that masks the original failure. Even if it is idempotent, calling it without knowing the run's current state violates the principle of explicit state management. A more robust approach would check the current status first.

**Evidence:**
```python
# Line 472 -- finalize_run on success (only reached if _execute_run returns normally)
recorder.finalize_run(run.run_id, status=RunStatus.COMPLETED)
# ...
# Line 582 -- finalize_run on failure (reached if _execute_run raises)
recorder.finalize_run(run.run_id, status=RunStatus.FAILED)
```

### [1073-1156] Source quarantine handling does not record schema contract

**What:** When a source row is quarantined (line 1074), the schema contract recording at lines 1167-1177 is skipped (it only triggers for valid rows). If ALL source rows are quarantined, the schema contract will never be recorded for the run. If the run later needs to be resumed (or if the audit trail is queried), the missing contract could cause issues.

**Why it matters:** The resume path at line 1733 crashes with `OrchestrationInvariantError` if the schema contract is missing from the audit trail. This means a run where all source rows were quarantined (e.g., a malformed CSV file) cannot be resumed. While this may be an acceptable limitation (there's nothing to resume -- all rows failed), the crash message at line 1740-1747 says "audit database is corrupt or incomplete", which is misleading. The real cause is that no valid rows existed.

**Evidence:**
```python
# Line 1167-1170
if not schema_contract_recorded:
    schema_contract = config.source.get_schema_contract()
    if schema_contract is not None:  # Only records for valid rows
        schema_contract_recorded = True
```

### [2010-2017] No checkpointing during resume

**What:** The code explicitly documents that resume processing does not create checkpoints (lines 2010-2017). If resume crashes during processing, it must start over from the original checkpoint.

**Why it matters:** For runs with many unprocessed rows during resume, this means all progress is lost on a crash. The comment acknowledges this as an intentional simplicity trade-off, but for a system designed for high-stakes accountability pipelines, losing progress on crash during recovery is a meaningful limitation. If a pipeline crashed once, it could crash again during resume.

## Observations

### [256-272] `_cleanup_transforms` only closes transforms, not sinks

**What:** The method name `_cleanup_transforms` accurately describes what it does -- it only calls `close()` on transforms and gates, not on sinks or the source. The `_execute_run` finally block handles sinks and source separately. However, if `_execute_run` raises during setup (before the finally block), sinks that had `on_start` called would not get `close()` called.

**Why it matters:** This is mitigated by the fact that `_execute_run` calls `on_start` relatively late (lines 862-868), and failures before that point would not have opened plugin resources. However, if `on_start` succeeds but the subsequent RowProcessor creation fails, sink resources opened in `on_start` would leak. Low probability given current code structure, but worth noting.

### [565] Stale line reference in comment

**What:** Line 563 contains the comment "NOTE: RunFinished was already emitted at lines 604-612 before the export attempt". The actual `RunFinished` telemetry emission is at lines 478-486 in the current version of the code, not lines 604-612.

**Why it matters:** Stale line references in comments are misleading during code review and debugging. This suggests the code was reorganized at some point and the comments were not updated.

### [84] `landscape=None` in export PluginContext

**What:** In `export_landscape()` at line 84, a `PluginContext` is created with `landscape=None`. This means any sink that tries to use the landscape during the export phase will crash.

**Why it matters:** Sinks in the export path should not need landscape access (they are writing the landscape data, not querying it). But the `None` value is a latent crash if any sink code path inadvertently accesses `ctx.landscape`. This is documented behavior and acceptable given the export context, but worth noting.

### [105] Unused variable in export path

**What:** At line 105, `_artifact_descriptor = sink.write(records, ctx)` assigns the result to a variable prefixed with underscore. The comment says "Capture ArtifactDescriptor for audit trail (future use)".

**Why it matters:** This is dead code (or dead assignment). Per the project's "No Legacy Code" policy, unused code should be removed. The underscore prefix indicates awareness that it's unused, but the variable still exists.

### [959-961] Hardcoded progress emission intervals

**What:** Progress is emitted every 100 rows or every 5 seconds (lines 959-960). These values are hardcoded rather than configurable.

**Why it matters:** For large pipelines (millions of rows), every-100-rows may be too frequent. For small pipelines, every-5-seconds may never trigger. This is minor and appropriate for RC-2, but should be documented as configurable in a future release.

### [1548] `from itertools import groupby` inside loop-adjacent code

**What:** The `from itertools import groupby` import at line 1548 is inside the method body (after the main processing loop). Similarly at line 2229. This pattern is used throughout the codebase for deferred imports.

**Why it matters:** No functional issue, but importing inside the function body is mildly surprising. It avoids circular imports and reduces startup cost, which is the established pattern in this codebase.

### [1646-1647] `_current_graph = None` only reached on success

**What:** Line 1647 clears `self._current_graph` after the finally block. But if the finally block raises (due to cleanup errors), this line is never reached, leaving `_current_graph` set.

**Why it matters:** If the Orchestrator instance is reused (e.g., in tests), the stale graph reference could cause confusion. In production, the Orchestrator is likely not reused after a failed run. Low impact.

### [400-406 + 667-672] Telemetry imports inside method bodies

**What:** Telemetry event classes are imported inside `run()` (line 402) and `_execute_run()` (line 668). The comment says "consolidated here to avoid repeated imports."

**Why it matters:** This is a pattern choice, not a bug. The imports are at the top of each method rather than at module level, likely to avoid importing telemetry classes when telemetry is disabled. This is consistent with the codebase's pattern of deferred imports.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. **Fix immediately:** Missing `rows_succeeded` increments in `_process_resumed_rows()` coalesce-timeout handlers (lines 2120 and 2139). These are counter bugs that produce incorrect metrics.
2. **Fix soon:** Resolve the double-close of transforms between `_execute_run()` finally and `run()` `_cleanup_transforms()`. Either remove `_cleanup_transforms()` from `run()` (since `_execute_run` already handles cleanup) or remove transform close from `_execute_run`'s finally block.
3. **Fix soon:** Address the cleanup-error-masks-BatchPendingError scenario (line 1642-1643). Cleanup errors should not replace control-flow signals.
4. **Refactor consideration:** Extract the duplicated outcome-handling logic (~800 lines duplicated between run and resume) into a shared helper. The current duplication has already caused divergence bugs and will cause more.
5. **Minor:** Fix `sys.exc_info()[0]` at line 621 to `sys.exc_info()[1]` for consistency.

**Confidence:** HIGH -- The critical findings are confirmed by direct code comparison between the run and resume paths. The counter bug is mechanically verifiable (line-by-line diff shows the missing increment). The double-close is confirmed by tracing the finally block execution order. The exception masking scenario is confirmed by Python exception handling semantics.
