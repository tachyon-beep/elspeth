# Executor Context DTOs — Typed context_after for Gate & Aggregation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace missing context_after metadata in gate and aggregation executors with typed frozen dataclass DTOs that satisfy the `NodeStateContext` protocol, closing the audit completeness gap.

**Architecture:** Two new frozen dataclasses (`GateEvaluationContext`, `AggregationFlushContext`) in `contracts/node_state_context.py`, following the established `PoolExecutionContext` and `CoalesceMetadata` precedent. Each executor constructs its DTO and passes it to `guard.complete()` or `recorder.complete_node_state()`.

**Tech Stack:** Python dataclasses (frozen=True, slots=True), NodeStateContext protocol, canonical_json serialization

**Bug:** elspeth-rapid-a326d8 — "context_before/after metadata is untyped dict across all executors"

---

## Scope Analysis

| Executor | Current context_after | Action |
|----------|----------------------|--------|
| TransformExecutor | `result.context_after` (PoolExecutionContext) | Already typed ✅ |
| CoalesceExecutor | `CoalesceMetadata` | Already typed ✅ |
| GateExecutor | `None` — evaluation metadata lost | **Add GateEvaluationContext** |
| AggregationExecutor | `None` — flush metadata lost | **Add AggregationFlushContext** |
| SinkExecutor | `None` — but artifacts/operations tables capture this | No change needed |

`context_before_json` is a dead column (always `None`, never populated). Removing it would require an Alembic migration — out of scope for this bug.

---

### Task 1: Create GateEvaluationContext DTO

**Files:**
- Modify: `src/elspeth/contracts/node_state_context.py`
- Test: `tests/unit/contracts/test_node_state_context.py`

**Step 1: Write the failing tests**

Add to `tests/unit/contracts/test_node_state_context.py`:

```python
from elspeth.contracts.node_state_context import GateEvaluationContext


class TestGateEvaluationContext:
    def test_to_dict(self) -> None:
        ctx = GateEvaluationContext(
            condition="row['score'] > 100",
            result="true",
            route_label="true",
        )
        d = ctx.to_dict()
        assert d == {
            "condition": "row['score'] > 100",
            "result": "true",
            "route_label": "true",
        }

    def test_frozen(self) -> None:
        ctx = GateEvaluationContext(
            condition="row['x'] > 0",
            result="false",
            route_label="false",
        )
        with pytest.raises(FrozenInstanceError):
            ctx.condition = "changed"  # type: ignore[misc]

    def test_canonical_json_produces_valid_json(self) -> None:
        ctx = GateEvaluationContext(
            condition="row['score'] > 100",
            result="true",
            route_label="true",
        )
        json_str = canonical_json(ctx.to_dict())
        parsed = json.loads(json_str)
        assert parsed == ctx.to_dict()

    def test_canonical_json_deterministic(self) -> None:
        ctx = GateEvaluationContext(
            condition="row['x'] > 0",
            result="false",
            route_label="false",
        )
        json1 = canonical_json(ctx.to_dict())
        json2 = canonical_json(ctx.to_dict())
        assert json1 == json2
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_node_state_context.py::TestGateEvaluationContext -v`
Expected: FAIL with ImportError (GateEvaluationContext doesn't exist yet)

**Step 3: Write the implementation**

Add to `src/elspeth/contracts/node_state_context.py` (after `PoolExecutionContext`):

```python
@dataclass(frozen=True, slots=True)
class GateEvaluationContext:
    """Typed context metadata for gate evaluation audit records.

    Captures the gate's condition expression and evaluation result
    for the audit trail.  Follows the same pattern as
    ``PoolExecutionContext`` and ``CoalesceMetadata``.
    """

    condition: str
    result: str
    route_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "result": self.result,
            "route_label": self.route_label,
        }
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_node_state_context.py::TestGateEvaluationContext -v`
Expected: PASS (all 4 tests)

**Step 5: Add protocol conformance test**

Add to `TestProtocolConformance` class in same file:

```python
def test_gate_evaluation_context_has_to_dict(self) -> None:
    """GateEvaluationContext satisfies NodeStateContext protocol."""
    ctx = GateEvaluationContext(
        condition="row['x'] > 0",
        result="true",
        route_label="true",
    )
    d = ctx.to_dict()
    assert isinstance(d, dict)
    assert "condition" in d
```

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_node_state_context.py::TestProtocolConformance -v`
Expected: PASS

**Step 6: Export from contracts/__init__.py**

Add `GateEvaluationContext` to the import from `node_state_context` and to `__all__` in `src/elspeth/contracts/__init__.py`.

**Step 7: Commit**

```bash
git add src/elspeth/contracts/node_state_context.py src/elspeth/contracts/__init__.py tests/unit/contracts/test_node_state_context.py
git commit -m "feat: add GateEvaluationContext DTO for typed gate audit metadata

Closes gap where gate evaluation metadata (condition, result, route)
was not recorded in context_after_json. Follows PoolExecutionContext
and CoalesceMetadata precedent.

Part of: elspeth-rapid-a326d8"
```

---

### Task 2: Create AggregationFlushContext DTO

**Files:**
- Modify: `src/elspeth/contracts/node_state_context.py`
- Modify: `src/elspeth/contracts/__init__.py`
- Test: `tests/unit/contracts/test_node_state_context.py`

**Step 1: Write the failing tests**

Add to `tests/unit/contracts/test_node_state_context.py`:

```python
from elspeth.contracts.node_state_context import AggregationFlushContext


class TestAggregationFlushContext:
    def test_to_dict(self) -> None:
        ctx = AggregationFlushContext(
            trigger_type="count",
            buffer_size=10,
            batch_id="batch_abc123",
        )
        d = ctx.to_dict()
        assert d == {
            "trigger_type": "count",
            "buffer_size": 10,
            "batch_id": "batch_abc123",
        }

    def test_frozen(self) -> None:
        ctx = AggregationFlushContext(
            trigger_type="timeout",
            buffer_size=5,
            batch_id="batch_xyz",
        )
        with pytest.raises(FrozenInstanceError):
            ctx.buffer_size = 99  # type: ignore[misc]

    def test_canonical_json_produces_valid_json(self) -> None:
        ctx = AggregationFlushContext(
            trigger_type="end_of_source",
            buffer_size=3,
            batch_id="batch_001",
        )
        json_str = canonical_json(ctx.to_dict())
        parsed = json.loads(json_str)
        assert parsed == ctx.to_dict()

    def test_canonical_json_deterministic(self) -> None:
        ctx = AggregationFlushContext(
            trigger_type="count",
            buffer_size=10,
            batch_id="batch_abc",
        )
        json1 = canonical_json(ctx.to_dict())
        json2 = canonical_json(ctx.to_dict())
        assert json1 == json2
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_node_state_context.py::TestAggregationFlushContext -v`
Expected: FAIL with ImportError

**Step 3: Write the implementation**

Add to `src/elspeth/contracts/node_state_context.py`:

```python
@dataclass(frozen=True, slots=True)
class AggregationFlushContext:
    """Typed context metadata for aggregation flush audit records.

    Captures the trigger that fired and batch metadata for the
    audit trail.  Follows the same pattern as ``PoolExecutionContext``
    and ``CoalesceMetadata``.
    """

    trigger_type: str
    buffer_size: int
    batch_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type,
            "buffer_size": self.buffer_size,
            "batch_id": self.batch_id,
        }
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_node_state_context.py::TestAggregationFlushContext -v`
Expected: PASS

**Step 5: Add protocol conformance test**

Add to `TestProtocolConformance` class:

```python
def test_aggregation_flush_context_has_to_dict(self) -> None:
    """AggregationFlushContext satisfies NodeStateContext protocol."""
    ctx = AggregationFlushContext(
        trigger_type="count",
        buffer_size=5,
        batch_id="batch_001",
    )
    d = ctx.to_dict()
    assert isinstance(d, dict)
    assert "trigger_type" in d
```

**Step 6: Export from contracts/__init__.py**

Add `AggregationFlushContext` to the import from `node_state_context` and to `__all__`.

**Step 7: Commit**

```bash
git add src/elspeth/contracts/node_state_context.py src/elspeth/contracts/__init__.py tests/unit/contracts/test_node_state_context.py
git commit -m "feat: add AggregationFlushContext DTO for typed batch audit metadata

Closes gap where aggregation flush metadata (trigger_type, buffer_size,
batch_id) was not recorded in context_after_json.

Part of: elspeth-rapid-a326d8"
```

---

### Task 3: Wire GateEvaluationContext into GateExecutor

**Files:**
- Modify: `src/elspeth/engine/executors/gate.py`
- Test: `tests/unit/engine/executors/test_gate.py` (or wherever gate tests live)

**Step 1: Write the failing test**

Find the existing gate executor tests and add a test that verifies `context_after_json` is recorded. The test should:
1. Execute a config gate via `execute_config_gate()`
2. Retrieve the completed node state from the recorder
3. Assert `context_after_json` is not None
4. Assert the deserialized JSON contains `condition`, `result`, and `route_label`

```python
def test_execute_config_gate_records_context_after(self, ...):
    """Gate evaluation metadata should be recorded in context_after_json."""
    # ... setup gate_config, token, ctx ...
    outcome = executor.execute_config_gate(gate_config, node_id, token, ctx)

    # Get completed node state
    state = recorder.get_node_state(...)  # retrieve by state_id
    assert state.context_after_json is not None

    import json
    context = json.loads(state.context_after_json)
    assert context["condition"] == gate_config.condition
    assert "result" in context
    assert "route_label" in context
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `context_after_json` is currently `None` for gate states

**Step 3: Modify gate executor to pass GateEvaluationContext**

In `src/elspeth/engine/executors/gate.py`, in `execute_config_gate()`:

1. After the condition is evaluated and route_label is determined (around line 295), create the context:

```python
from elspeth.contracts.node_state_context import GateEvaluationContext

gate_context = GateEvaluationContext(
    condition=gate_config.condition,
    result=str(eval_result),
    route_label=route_label,
)
```

2. Pass it to `complete_node_state()` at line 346:

```python
self._recorder.complete_node_state(
    state_id=state.state_id,
    status=NodeStateStatus.COMPLETED,
    output_data=input_dict,
    duration_ms=duration_ms,
    context_after=gate_context,  # NEW
)
```

**Step 4: Run test to verify it passes**

Expected: PASS

**Step 5: Run full gate test suite**

Run: `.venv/bin/python -m pytest tests/unit/engine/executors/test_gate.py -v` (or equivalent path)
Expected: All existing tests PASS (context_after is additive, no behavior change)

**Step 6: Commit**

```bash
git add src/elspeth/engine/executors/gate.py tests/...
git commit -m "feat: wire GateEvaluationContext into gate executor

Gate evaluation metadata (condition, result, route_label) is now
recorded in context_after_json for audit completeness.

Part of: elspeth-rapid-a326d8"
```

---

### Task 4: Wire AggregationFlushContext into AggregationExecutor

**Files:**
- Modify: `src/elspeth/engine/executors/aggregation.py`
- Test: `tests/unit/engine/executors/test_aggregation.py` (or equivalent)

**Step 1: Write the failing test**

Add a test that verifies `context_after_json` is recorded on successful flush:

```python
def test_execute_flush_records_context_after(self, ...):
    """Aggregation flush metadata should be recorded in context_after_json."""
    # ... buffer rows, trigger flush ...
    result, tokens, batch_id = executor.execute_flush(node_id, transform, ctx, TriggerType.COUNT)

    # Get completed node state
    state = recorder.get_node_state(...)
    assert state.context_after_json is not None

    import json
    context = json.loads(state.context_after_json)
    assert context["trigger_type"] == "COUNT"
    assert context["buffer_size"] == len(tokens)
    assert context["batch_id"] == batch_id
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `context_after_json` is currently `None` for aggregation states

**Step 3: Modify aggregation executor to pass AggregationFlushContext**

In `src/elspeth/engine/executors/aggregation.py`, in `execute_flush()`:

1. Before `guard.complete()` calls (both success and error paths), create the context:

```python
from elspeth.contracts.node_state_context import AggregationFlushContext

flush_context = AggregationFlushContext(
    trigger_type=trigger_type.value,
    buffer_size=len(buffered_rows),
    batch_id=batch_id,
)
```

2. Pass to each `guard.complete()` call:
   - Success path (line 464): `guard.complete(..., context_after=flush_context)`
   - Error path (line 485): `guard.complete(..., context_after=flush_context)`

**Step 4: Run test to verify it passes**

Expected: PASS

**Step 5: Run full aggregation test suite**

Run: `.venv/bin/python -m pytest tests/unit/engine/executors/test_aggregation.py -v` (or equivalent)
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add src/elspeth/engine/executors/aggregation.py tests/...
git commit -m "feat: wire AggregationFlushContext into aggregation executor

Aggregation flush metadata (trigger_type, buffer_size, batch_id) is now
recorded in context_after_json for audit completeness.

Part of: elspeth-rapid-a326d8"
```

---

### Task 5: Verification Gate

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All tests pass

**Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/contracts/node_state_context.py src/elspeth/engine/executors/gate.py src/elspeth/engine/executors/aggregation.py`
Expected: No errors

**Step 3: Run ruff**

Run: `.venv/bin/python -m ruff check src/elspeth/contracts/node_state_context.py src/elspeth/engine/executors/gate.py src/elspeth/engine/executors/aggregation.py`
Expected: No errors

**Step 4: Run config contracts checker**

Run: `.venv/bin/python -m scripts.check_contracts`
Expected: Pass

**Step 5: Close Filigree issue**

```bash
filigree update elspeth-rapid-a326d8 --status=verifying
# After all checks pass:
filigree close elspeth-rapid-a326d8 --reason="Fixed in commits: GateEvaluationContext + AggregationFlushContext DTOs added, wired into executors"
```
