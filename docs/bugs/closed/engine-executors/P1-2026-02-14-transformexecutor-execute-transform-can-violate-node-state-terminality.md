## Summary

`TransformExecutor.execute_transform()` can violate node-state terminality by leaving a state `OPEN` or recording `COMPLETED` before all executor-critical work succeeds.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py`
- Line(s): `213-283`, `285-303`, `323-351`
- Function/Method: `TransformExecutor.execute_transform`

## Evidence

`transform.process()` is wrapped in a try/except, but all post-processing is outside that protection:

```python
# transform.py
try:
    result = transform.process(...)
except Exception:
    self._recorder.complete_node_state(...FAILED...)
    raise
```

After that, unguarded code can still raise:

- `PluginContractViolation` on non-canonical output (`transform.py:297-302`) before terminal state completion (`transform.py:323+`) -> leaves state `OPEN`.
- `update_node_output_contract()` is called after marking state `COMPLETED` (`transform.py:323-351`). If that call fails, executor raises after already recording success, so audit state can show `COMPLETED` even though execution aborted.

This conflicts with terminal-state guarantees in `CLAUDE.md` ("Every row reaches exactly one terminal state").

Also, existing executor tests focus on exceptions from `transform.process()` (`tests/unit/engine/test_executors.py:544-574`) and do not cover post-processing failure paths.

## Root Cause Hypothesis

Failure handling is scoped too narrowly (plugin call only). Hashing/validation/audit-write follow-up work that can fail is outside the failure-to-terminal-state path.

## Suggested Fix

Refactor `execute_transform()` so state completion is atomic with all executor-side validation:

1. Perform post-processing/validation in a guarded block.
2. If any exception occurs before terminal completion, call `complete_node_state(...FAILED...)` with contextual `ExecutionError`, then re-raise.
3. For success path, move `complete_node_state(...COMPLETED...)` to the end, after contract-evolution updates succeed, so no "completed-then-crash" window exists.

## Impact

- Audit trail may contain `OPEN` node states on plugin-output contract errors.
- Audit can show `COMPLETED` for a transform that actually failed during executor follow-up work.
- Breaks "no silent/incomplete state transitions" expectations and weakens incident explainability.
