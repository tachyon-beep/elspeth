# AggregationExecutor Parallel Dict Consolidation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 6 parallel dicts keyed by `NodeID` in `AggregationExecutor` with a single `dict[NodeID, _AggregationNodeState]`, eliminating the parallel-arrays anti-pattern that risks buffer/token desync at the Tier 1 boundary.

**Architecture:** `AggregationExecutor` currently scatters per-node state across 6 parallel dicts (`_aggregation_settings`, `_trigger_evaluators`, `_batch_ids`, `_buffers`, `_buffer_tokens`, `_restored_states`) plus a 7th dict `_member_counts` keyed by `batch_id`. We consolidate into `self._nodes: dict[NodeID, _AggregationNodeState]` where `_AggregationNodeState` is a mutable dataclass. Follows the exact same pattern as commit `32f97ca8` which consolidated `_PendingCoalesce` parallel dicts.

**Tech Stack:** Python dataclasses, no new dependencies.

**Bug:** `elspeth-rapid-e7f6bd` — "AggregationExecutor has 6 parallel dicts keyed by NodeID — consolidate into single-entry dataclass"

---

## Risk Assessment

- **Scope:** 1 production file (`aggregation.py`), 1 integration test line, 0 contract changes
- **Access sites:** ~71 references to the 7 parallel dicts, all within `aggregation.py`
- **External access:** 1 line in `tests/integration/pipeline/test_aggregation_recovery.py:635` (`executor._trigger_evaluators.get(...)`)
- **Behavioral change:** None — pure structural refactor, identical runtime behavior
- **Test coverage:** `TestAggregationExecutor` (unit), `test_aggregation_recovery.py` (integration), `test_aggregation_state_properties.py` (property), `test_aggregation_contracts.py` (integration)

---

## Task 1: Add `_AggregationNodeState` dataclass and replace constructor

**Files:**
- Modify: `src/elspeth/engine/executors/aggregation.py`

**Step 1: Add the dataclass above the class definition (after imports, before `class AggregationExecutor`)**

Insert at line 48 (after `AGGREGATION_CHECKPOINT_VERSION`):

```python
@dataclass(slots=True)
class _AggregationNodeState:
    """Per-node aggregation state.

    Groups settings, trigger evaluator, batch tracking, and row buffers
    that were previously scattered across six parallel dicts keyed by NodeID,
    plus a member_count that was in a separate dict keyed by batch_id.

    Mutable because buffers grow during processing and batch_id/member_count
    change across batch lifecycles.  Not frozen (unlike _BranchEntry in
    coalesce_executor.py) because the fields are updated in-place.
    """

    settings: AggregationSettings
    trigger: TriggerEvaluator
    batch_id: str | None = None
    member_count: int = 0
    buffers: list[dict[str, Any]] = field(default_factory=list)
    tokens: list[TokenInfo] = field(default_factory=list)
    restored_state: AggregationCheckpointState | None = None
```

Add `from dataclasses import dataclass, field` to imports.

**Step 2: Replace the 7 parallel dicts in `__init__` with `self._nodes`**

Replace lines 96–111 (the 7 dict declarations + init loop) with:

```python
        self._nodes: dict[NodeID, _AggregationNodeState] = {}
        for node_id, settings in (aggregation_settings or {}).items():
            self._nodes[node_id] = _AggregationNodeState(
                settings=settings,
                trigger=TriggerEvaluator(settings.trigger, clock=self._clock),
            )
```

Remove the `aggregation_settings` parameter's storage and the separate loop.

**Step 3: Run tests — expect widespread failures from removed dict names**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py::TestAggregationExecutor -x --tb=line -q 2>&1 | tail -5`
Expected: FAIL — methods still reference old dict names.

---

## Task 2: Update `buffer_row` and helper methods

**Files:**
- Modify: `src/elspeth/engine/executors/aggregation.py`

**Step 1: Rewrite `buffer_row` to use `self._nodes`**

All `self._aggregation_settings` checks become `self._nodes`. All `self._batch_ids[node_id]`, `self._buffers[node_id]`, etc. become `node = self._nodes[node_id]` then `node.batch_id`, `node.buffers`, etc.

Key mappings:
- `node_id not in self._aggregation_settings` → `node_id not in self._nodes`
- `self._batch_ids[node_id]` → `node.batch_id`
- `self._batch_ids[node_id] = batch.batch_id` → `node.batch_id = batch.batch_id`
- `self._member_counts[batch.batch_id] = 0` → `node.member_count = 0`
- `self._buffers[node_id].append(...)` → `node.buffers.append(...)`
- `self._buffer_tokens[node_id].append(...)` → `node.tokens.append(...)`
- `self._member_counts[batch_id]` → `node.member_count`
- `self._member_counts[batch_id] = ordinal + 1` → `node.member_count = ordinal + 1`
- `self._trigger_evaluators[node_id].record_accept()` → `node.trigger.record_accept()`

**Step 2: Rewrite `get_buffered_rows`, `get_buffered_tokens`, `_get_buffered_data`, `get_buffer_count`**

Pattern for each:
```python
def get_buffered_rows(self, node_id: NodeID) -> list[dict[str, Any]]:
    if node_id not in self._nodes:
        raise OrchestrationInvariantError(...)
    return list(self._nodes[node_id].buffers)
```

**Step 3: Rewrite `_reset_batch_state`**

```python
def _reset_batch_state(self, node_id: NodeID) -> None:
    node = self._nodes[node_id]
    assert node.batch_id is not None, f"_reset_batch_state invariant violation: batch_id is None for {node_id}"
    node.batch_id = None
    node.member_count = 0
```

**Step 4: Run tests to check progress**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py::TestAggregationExecutor -x --tb=line -q 2>&1 | tail -10`

---

## Task 3: Update `execute_flush`

**Files:**
- Modify: `src/elspeth/engine/executors/aggregation.py`

**Step 1: Rewrite `execute_flush` to use `self._nodes`**

Key mappings:
- `self._batch_ids.get(node_id)` → `self._nodes[node_id].batch_id`
- `self._buffers[node_id]` → `node.buffers`
- `self._buffer_tokens[node_id]` → `node.tokens`
- Error cleanup block: `self._buffers[node_id] = []` → `node.buffers.clear()`
- Error cleanup block: `self._buffer_tokens[node_id] = []` → `node.tokens.clear()`
- `self._trigger_evaluators[node_id].reset()` → `node.trigger.reset()`
- Success cleanup: same pattern as error cleanup
- `_reset_batch_state(node_id)` → unchanged (already updated in Task 2)

Get `node` at the top of the method:
```python
node = self._nodes[node_id]
batch_id = node.batch_id
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py::TestAggregationExecutor -x --tb=short -q 2>&1 | tail -10`

---

## Task 4: Update checkpoint and restore methods

**Files:**
- Modify: `src/elspeth/engine/executors/aggregation.py`

**Step 1: Rewrite `get_checkpoint_state`**

Change the iteration from `self._buffer_tokens.items()` to `self._nodes.items()`:

```python
for node_id, node in self._nodes.items():
    if not node.tokens:  # Only include non-empty buffers
        continue
    evaluator = node.trigger
    # ... rest uses node.batch_id, node.tokens, etc.
```

The total rows calculation changes from:
```python
total_rows = sum(len(b) for b in self._buffer_tokens.values())
```
to:
```python
total_rows = sum(len(n.tokens) for n in self._nodes.values())
```

**Step 2: Rewrite `restore_from_checkpoint`**

Key mappings:
- `self._buffer_tokens[node_id]` → `node.tokens`
- `self._buffers[node_id]` → `node.buffers`
- `self._batch_ids[node_id]` → `node.batch_id`
- `self._member_counts[node_checkpoint.batch_id]` → `node.member_count`
- `self._trigger_evaluators[node_id]` → `node.trigger`

Get node at top of loop body:
```python
node = self._nodes[node_id]
```

**Step 3: Rewrite `restore_state` and `get_restored_state`**

```python
def restore_state(self, node_id: NodeID, state: AggregationCheckpointState) -> None:
    node = self._nodes.get(node_id)
    if node is None:
        slog.warning("restore_state_unknown_node", node_id=str(node_id))
        return
    node.restored_state = state

def get_restored_state(self, node_id: NodeID) -> AggregationCheckpointState | None:
    node = self._nodes.get(node_id)
    if node is None:
        return None
    return node.restored_state
```

**Step 4: Rewrite `restore_batch`**

```python
def restore_batch(self, batch_id: str) -> None:
    batch = self._recorder.get_batch(batch_id)
    if batch is None:
        raise ValueError(f"Batch not found: {batch_id}")
    node_id = NodeID(batch.aggregation_node_id)
    node = self._nodes[node_id]
    node.batch_id = batch_id
    members = self._recorder.get_batch_members(batch_id)
    node.member_count = len(members)
```

**Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py::TestAggregationExecutor -x --tb=short -q 2>&1 | tail -10`

---

## Task 5: Update remaining methods and trigger access

**Files:**
- Modify: `src/elspeth/engine/executors/aggregation.py`

**Step 1: Rewrite `get_batch_id`, `should_flush`, `get_trigger_type`, `check_flush_status`**

Pattern:
```python
def get_batch_id(self, node_id: NodeID) -> str | None:
    node = self._nodes.get(node_id)
    if node is None:
        return None
    return node.batch_id

def should_flush(self, node_id: NodeID) -> bool:
    if node_id not in self._nodes:
        raise OrchestrationInvariantError(...)
    return self._nodes[node_id].trigger.should_trigger()

def get_trigger_type(self, node_id: NodeID) -> TriggerType | None:
    if node_id not in self._nodes:
        raise OrchestrationInvariantError(...)
    return self._nodes[node_id].trigger.get_trigger_type()

def check_flush_status(self, node_id: NodeID) -> tuple[bool, TriggerType | None]:
    if node_id not in self._nodes:
        raise OrchestrationInvariantError(...)
    node = self._nodes[node_id]
    should_flush = node.trigger.should_trigger()
    trigger_type = node.trigger.get_trigger_type() if should_flush else None
    return (should_flush, trigger_type)
```

**Step 2: Run full AggregationExecutor unit tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py::TestAggregationExecutor tests/unit/engine/test_executors.py::TestAggregationCheckpointVersion tests/unit/engine/test_executors.py::TestAggregationExecutorTerminality -v --tb=short 2>&1 | tail -20`

---

## Task 6: Fix external test access and run full suite

**Files:**
- Modify: `tests/integration/pipeline/test_aggregation_recovery.py:635`

**Step 1: Update integration test that accesses internal `_trigger_evaluators`**

Change line 635 from:
```python
restored_evaluator = executor._trigger_evaluators.get(NodeID("sum_aggregator"))
```
to:
```python
node_state = executor._nodes.get(NodeID("sum_aggregator"))
assert node_state is not None
restored_evaluator = node_state.trigger
```

**Step 2: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x --tb=short -q 2>&1 | tail -10`

**Step 3: Run type checker**

Run: `.venv/bin/python -m mypy src/elspeth/engine/executors/aggregation.py --no-error-summary 2>&1 | tail -20`

**Step 4: Run linter**

Run: `.venv/bin/python -m ruff check src/elspeth/engine/executors/aggregation.py 2>&1`

---

## Task 7: Verify error message consistency

**Step 1: Verify all `OrchestrationInvariantError` messages say "not in aggregation_settings"→"not in configured aggregation nodes" or keep the same wording**

The existing error messages reference `aggregation_settings` by name. Since the internal data structure changed but the concept hasn't (configured aggregation nodes), keep the error messages unchanged — they describe the *semantic* issue, not the internal data structure name.

Grep to verify: All validation checks use `node_id not in self._nodes` but error messages still say "not in aggregation_settings" (matching the constructor parameter name that users/callers see).

**Step 2: Run targeted tests for error paths**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py -k "unconfigured" -v --tb=short 2>&1 | tail -15`

---

## Summary of Changes

| Before | After |
|--------|-------|
| `self._aggregation_settings: dict[NodeID, AggregationSettings]` | `self._nodes[nid].settings` |
| `self._trigger_evaluators: dict[NodeID, TriggerEvaluator]` | `self._nodes[nid].trigger` |
| `self._batch_ids: dict[NodeID, str \| None]` | `self._nodes[nid].batch_id` |
| `self._member_counts: dict[str, int]` | `self._nodes[nid].member_count` |
| `self._buffers: dict[NodeID, list[dict]]` | `self._nodes[nid].buffers` |
| `self._buffer_tokens: dict[NodeID, list[TokenInfo]]` | `self._nodes[nid].tokens` |
| `self._restored_states: dict[NodeID, AggregationCheckpointState]` | `self._nodes[nid].restored_state` |
