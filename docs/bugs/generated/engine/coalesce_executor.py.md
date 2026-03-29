## Summary

`_execute_merge()` can raise after `accept()` has already opened coalesce node states, leaving those states `OPEN` with no terminal token outcome recorded.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/engine/coalesce_executor.py`
- Line(s): 432-454, 638-739, 763-782
- Function/Method: `_execute_merge`

## Evidence

`accept()` opens a node state for each arriving branch before deciding whether to merge:

```python
# src/elspeth/engine/coalesce_executor.py:432-443
state = self._recorder.begin_node_state(...)
pending.branches[token.branch_name] = _BranchEntry(...)
if self._should_merge(settings, pending):
    return self._execute_merge(...)
```

`_execute_merge()` then performs several operations that can legitimately throw before any terminal state is recorded:

```python
# src/elspeth/engine/coalesce_executor.py:638-739
merged_data_dict, union_collisions = self._merge_data(...)
merged_contract = merged_contract.merge(c)   # can raise
merged_data = PipelineRow(merged_data_dict, merged_contract)  # can raise
merged_token = self._token_manager.coalesce_tokens(...)       # can raise
```

The node states are only completed much later:

```python
# src/elspeth/engine/coalesce_executor.py:763-782
self._recorder.complete_node_state(...)
self._recorder.record_token_outcome(..., outcome=RowOutcome.COALESCED, ...)
```

So any exception in the merge window leaves the previously-opened node states uncompleted. The repo already documents this exact failure mode as an audit-integrity bug and fixes it elsewhere with `NodeStateGuard`:

```python
# src/elspeth/engine/executors/state_guard.py:3-10
# failures ... left node_states permanently OPEN — violating the audit trail.
# NodeStateGuard encodes the invariant structurally
```

Other executors use that guard explicitly:

- `src/elspeth/engine/executors/transform.py:182-194`
- `src/elspeth/engine/executors/aggregation.py:339-351`

`coalesce_executor.py` does not.

## Root Cause Hypothesis

The coalesce path still uses manual `begin_node_state()` / `complete_node_state()` sequencing instead of the structural terminality guard adopted by the other executors. That leaves a crash window between “state opened” and “state completed”.

## Suggested Fix

Wrap each coalesce branch node state in `NodeStateGuard`, or add equivalent fail-closed cleanup around `_execute_merge()` so every opened coalesce state is auto-completed as `FAILED` if merge construction or token creation throws.

If keeping the current structure, the minimum safe behavior is:

```python
try:
    merged_token = self._token_manager.coalesce_tokens(...)
except Exception as exc:
    for entry in pending.branches.values():
        self._recorder.complete_node_state(
            state_id=entry.state_id,
            status=NodeStateStatus.FAILED,
            error=ExecutionError(...),
            duration_ms=(now - entry.arrival_time) * 1000,
        )
    raise
```

A `NodeStateGuard`-style structural guarantee is safer than hand-written cleanup.

## Impact

A contract merge failure, `PipelineRow` construction failure, or recorder/token-manager failure can leave coalesce branch states permanently `OPEN` and omit terminal `FAILED` / `COALESCED` outcomes. That breaks the “every token reaches exactly one terminal state” invariant and creates audit-trail gaps that make lineage explanations incomplete or misleading.
---
## Summary

`restore_from_checkpoint()` trusts checkpoint branch identities and row identities without revalidating them against the registered coalesce configuration, so corrupted Tier 1 checkpoint data can be restored as live pending state instead of crashing immediately.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `src/elspeth/engine/coalesce_executor.py`
- Line(s): 244-294
- Function/Method: `restore_from_checkpoint`

## Evidence

The restore path validates only the coalesce name:

```python
# src/elspeth/engine/coalesce_executor.py:264-269
if pending_entry.coalesce_name not in self._settings:
    raise AuditIntegrityError(...)
```

It then restores arbitrary branch entries directly from checkpoint payload:

```python
# src/elspeth/engine/coalesce_executor.py:272-294
for branch_name, token_checkpoint in pending_entry.branches.items():
    token = TokenInfo(
        row_id=token_checkpoint.row_id,
        branch_name=token_checkpoint.branch_name,
        ...
    )
    branches[branch_name] = _BranchEntry(...)
self._pending[(pending_entry.coalesce_name, pending_entry.row_id)] = _PendingCoalesce(...)
```

What is missing:

- No check that `branch_name` is in `self._settings[coalesce_name].branches`
- No check that `token_checkpoint.branch_name == branch_name`
- No check that `token_checkpoint.row_id == pending_entry.row_id`

The live path does enforce branch validity on arrival:

```python
# src/elspeth/engine/coalesce_executor.py:357-361
if token.branch_name not in settings.branches:
    raise OrchestrationInvariantError(...)
```

But checkpoint contracts do not enforce membership, only shape/non-empty strings:

- `src/elspeth/contracts/coalesce_checkpoint.py:34-50`
- `src/elspeth/contracts/coalesce_checkpoint.py:107-120`

The unit restore tests only cover version mismatch and unknown coalesce name, not invalid branch or row identity in checkpoint payload:

- `tests/unit/engine/test_coalesce_executor.py:1792-1848`

## Root Cause Hypothesis

The restore logic treats deserialized checkpoint contents as structurally valid once the dataclasses parse, but Tier 1 restoration also needs semantic validation against the current registered coalesce settings and key invariants. That second validation step is missing.

## Suggested Fix

In `restore_from_checkpoint()`, reject checkpoint entries unless all of the following hold before mutating `_pending`:

- outer `branch_name` exists in the registered `settings.branches`
- `token_checkpoint.branch_name == branch_name`
- `token_checkpoint.row_id == pending_entry.row_id`
- `lost_branches` keys are also a subset of `settings.branches`

Also validate `completed_keys` coalesce names before loading them, and preferably build a temporary restored structure first so restore is atomic on failure.

## Impact

A corrupted checkpoint can be resumed into an impossible in-memory barrier state instead of crashing at the Tier 1 boundary. That can later produce wrong merges, misleading branch metadata, or delayed invariant failures deeper in execution, which is worse than rejecting the checkpoint immediately because the audit trail now depends on bad restored state.
