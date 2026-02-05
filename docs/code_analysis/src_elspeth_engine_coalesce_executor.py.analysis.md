# Analysis: src/elspeth/engine/coalesce_executor.py

**Lines:** 903
**Role:** Fork/join barrier implementation. Manages coalesce points where tokens from parallel fork paths merge back into a single token. Implements merge policies (require_all, quorum, best_effort, first) and merge strategies (union, nested, select). Tracks pending tokens per (coalesce_name, row_id), evaluates merge conditions, executes merges, and records the complete audit trail via LandscapeRecorder.
**Key dependencies:**
- Imports: `TokenInfo`, `NodeStateStatus`, `RowOutcome`, `OrchestrationInvariantError`, `PipelineRow`, `SchemaContract`, `CoalesceSettings`, `LandscapeRecorder`, `SpanFactory`, `Clock`
- Imported by: `engine/processor.py` (RowProcessor), `engine/orchestrator/core.py` (Orchestrator), extensive test coverage in `tests/engine/test_coalesce_executor.py`, `test_coalesce_pipeline_row.py`, `test_processor_coalesce.py`, `test_coalesce_executor_audit_gaps.py`
**Analysis depth:** FULL

## Summary

The coalesce executor is well-structured with clear separation of concerns and thorough audit trail recording. Multiple historical bugs have been explicitly fixed and documented inline. The primary concerns are: (1) a missing handling path for the `first` policy in `check_timeouts` that would silently ignore timed-out entries under that policy, (2) union merge strategy silently drops data when branches have overlapping field names with different values, and (3) significant code duplication in failure-recording paths across `check_timeouts` and `flush_pending`. Overall the code is sound for its current use case but has specific edge cases that deserve attention.

## Critical Findings

### [543-550] Union merge silently overwrites fields from earlier branches with later branches

**What:** In `_merge_data` for the `union` strategy, branches are iterated in `settings.branches` order and `merged.update()` is called for each. If two branches produce the same field name with different values, the later branch silently wins with no audit record of the conflict.

**Why it matters:** For an audit system where "I don't know what happened" is never acceptable, silently dropping one branch's value for a field violates the auditability guarantee. Consider: branch A sets `classification = "urgent"` and branch B sets `classification = "routine"`. The merged result contains only branch B's value, and the audit trail shows no conflict was detected. An auditor reviewing the merged output would see `classification = "routine"` with no indication that branch A disagreed.

**Evidence:**
```python
if settings.merge == "union":
    merged: dict[str, Any] = {}
    for branch_name in settings.branches:
        if branch_name in arrived:
            merged.update(arrived[branch_name].row_data.to_dict())
    return merged
```

The `dict.update()` call silently overwrites any pre-existing keys. There is no conflict detection, no warning, and no audit metadata recording which branch's value was kept vs. discarded.

### [618] check_timeouts has no handling for `first` policy timeout - silently ignored

**What:** In `check_timeouts`, the method iterates over timed-out pending entries and handles `best_effort`, `quorum`, and `require_all` policies. However, the `first` policy has no branch in the `if/elif` chain. If a `first`-policy coalesce somehow has a pending entry (which `flush_pending` treats as an invariant violation via `RuntimeError`), `check_timeouts` will silently skip it.

**Why it matters:** While `first` policy is designed to merge immediately on first arrival (so pending entries should be impossible), the `flush_pending` method explicitly crashes on this invariant violation (line 891). The `check_timeouts` method should either do the same or at minimum log the anomaly. Silently ignoring a timed-out entry under any policy means tokens could be stuck in the barrier indefinitely with no diagnostic trail.

**Evidence:**
```python
# check_timeouts only handles:
if settings.policy == "best_effort" and len(pending.arrived) > 0:
    ...
elif settings.policy == "quorum":
    ...
elif settings.policy == "require_all":
    ...
# Missing: elif settings.policy == "first":
#     raise RuntimeError(...)  # Like flush_pending does
```

Compare with `flush_pending` (line 889-895):
```python
elif settings.policy == "first":
    raise RuntimeError(
        f"Invariant violation: 'first' policy should never have pending entries. ..."
    )
```

## Warnings

### [393-408] Contract merge exception is logged but may produce misleading audit metadata

**What:** When `SchemaContract.merge()` fails (e.g., conflicting field types across branches), the code logs the error and raises `OrchestrationInvariantError`. However, the `begin_node_state` records created for each held token (line 263-270) are left in OPEN/PENDING status with no completion. The recorder may have these dangling pending states in the audit trail.

**Why it matters:** If the orchestrator catches this error at a higher level and records a run failure, the pending node states for these tokens are never completed. This creates orphaned audit records -- states that began but have no completion record. Querying `explain_token` for these tokens would show them stuck in PENDING state, potentially confusing investigators.

**Evidence:** The exception propagates from `_execute_merge` back through `accept` to the caller. The `pending.pending_state_ids` entries created at line 270 are never completed because the `_execute_merge` path crashed before reaching the completion loop at line 493-505.

### [544-550] Union merge iteration order depends on settings.branches, not arrival order

**What:** The union merge iterates over `settings.branches` (the configured branch list) rather than `pending.arrived` keys. This means the "last branch wins" behavior is determined by the order branches are declared in config, not by which branch arrived last chronologically.

**Why it matters:** This could produce different merge results depending on YAML configuration ordering, which is a subtle source of non-determinism. If a pipeline operator reorders branches in config (perhaps alphabetizing them), the merge results change without any processing logic changing. This is a correctness concern in a system that values determinism and auditability.

**Evidence:**
```python
for branch_name in settings.branches:  # Config-defined order, not arrival order
    if branch_name in arrived:
        merged.update(arrived[branch_name].row_data.to_dict())
```

### [646-728] Significant code duplication in failure recording across check_timeouts and flush_pending

**What:** The failure-recording pattern (compute error hash, iterate over arrived tokens, complete node states with FAILED, record token outcomes with FAILED, delete pending, mark completed) is duplicated across at least five locations: `check_timeouts` quorum-not-met (lines 646-685), `check_timeouts` require_all (lines 689-728), `flush_pending` quorum-not-met (lines 787-836), `flush_pending` require_all (lines 838-887), and `_execute_merge` select-branch-not-arrived (lines 341-378).

**Why it matters:** The duplication increases the risk of inconsistency. Bug fixes applied to one path may be missed in another. This has already happened historically (Bug 6tb fix comment at line 647 explicitly notes the check_timeouts path was added to mirror flush_pending). The `outcomes_recorded` flag (Bug 9z8) was needed precisely because these parallel paths needed consistent behavior. Future changes to the failure-recording protocol will need to be applied in 5+ locations.

### [121-124] Bounded completed_keys set with 10,000 cap may be insufficient for large pipelines

**What:** The `_completed_keys` OrderedDict is bounded at 10,000 entries with FIFO eviction. After eviction, late arrivals that should have been rejected will instead create new pending entries that eventually timeout or flush.

**Why it matters:** For pipelines processing millions of rows with long timeout windows, 10,000 completed entries may be exhausted quickly. Late arrivals after eviction create spurious pending entries that consume memory and eventually produce failure outcomes, polluting the audit trail with false "incomplete_branches" failures rather than the correct "late_arrival_after_merge" diagnosis. The comment at line 123 acknowledges this trade-off but the 10,000 constant is not configurable.

**Evidence:**
```python
self._max_completed_keys: int = 10000
```

The hardcoded value has no connection to pipeline size, row count, or memory constraints. For a pipeline processing 1M rows with 3 branches, the completed set fills and starts evicting after ~3,333 source rows.

## Observations

### [31-52] CoalesceOutcome dataclass design is clean and well-documented

The outcome type clearly communicates the result of each operation. The `outcomes_recorded` flag (Bug 9z8 fix) is a pragmatic solution to the dual-recording problem. The documentation explicitly warns callers about the contract.

### [87-124] Constructor initializes all state cleanly with appropriate defaults

The clock injection pattern enables deterministic testing. The bounded completed_keys set is a good defense against OOM, even if the bound is somewhat arbitrary.

### [247-255] Duplicate arrival detection is correctly strict

Raising ValueError on duplicate branch arrivals is the right approach per the project's crash-on-our-bugs philosophy. The error message is diagnostic, identifying both the existing and new token IDs.

### [515-524] Merged token outcome recording is correctly deferred

The comment block at lines 515-521 clearly explains why the merged token does NOT get COALESCED recorded at merge time. This is correct for nested coalesce scenarios and shows careful reasoning about the token lifecycle.

### [897-901] Post-flush cleanup of completed_keys is correct

Clearing the completed_keys set after flush is correct because no more tokens will arrive after source exhaustion. This prevents O(rows) memory from lingering.

### [308-311] best_effort policy fallback to require_all check is subtle but correct

When `best_effort` has not timed out and not all branches have arrived, `_should_merge` returns False (line 310: `arrived_count == expected_count`). The merge happens only via timeout path or if all branches arrive. This is correct behavior but relies on the caller (`check_timeouts`) to handle the timeout case.

### Performance: No N+1 patterns detected

The `_execute_merge` method makes a fixed number of recorder calls proportional to the number of branches (not proportional to data size). The `check_timeouts` method iterates the pending dict once per check, which is appropriate.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. Add `first` policy handling to `check_timeouts` (raise RuntimeError like `flush_pending` does) -- this is a straightforward fix that prevents silent token loss.
2. Consider adding conflict detection to union merge, at minimum recording overlapping fields in the coalesce_metadata. This is important for audit integrity.
3. Consider extracting the duplicated failure-recording pattern into a private helper method to reduce the five-way duplication.
4. Make `_max_completed_keys` configurable or derive it from pipeline configuration.
**Confidence:** HIGH -- Full code read, full dependency context, multiple historical bug fixes demonstrate the code has been through significant iteration and edge case discovery. The findings are concrete and verifiable.
