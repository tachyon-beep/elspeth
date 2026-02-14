## Summary

`SinkExecutor.write()` can leave already-opened sink `node_states` in `OPEN` status when `begin_node_state()` fails mid-batch, violating terminal-state audit guarantees.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — begin_node_state is a Tier 1 DB operation where crash-on-failure is intended behavior; compensating writes to the same failing database would likely also fail; practical trigger requires mid-loop DB integrity issue)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/executors/sink.py
- Line(s): 148-160
- Function/Method: `SinkExecutor.write`

## Evidence

`SinkExecutor.write()` opens one `node_state` per token in a loop:

```python
# sink.py:148-160
states: list[tuple[TokenInfo, NodeStateOpen]] = []
for token in tokens:
    input_dict = token.row_data.to_dict()
    state = self._recorder.begin_node_state(...)
    states.append((token, state))
```

There is no `try/except` around this loop. If `begin_node_state()` fails after one or more successful inserts, execution exits immediately and previously opened states are never transitioned to `FAILED`.

`begin_node_state()` can fail on canonical hashing or DB insert:

```python
# _node_state_recording.py:86,103-116
input_hash = stable_hash(input_data)
self._ops.execute_insert(...)
```

So partial-open states are possible in real failures.

Observed repro (local mock run): second `begin_node_state` raises; result was `begin_calls=2`, `complete_calls=0`, and `sink.write` was never called. That means one state was left `OPEN` with no terminal completion path.

`SinkExecutor` already has `_complete_states_failed()` (`sink.py:73-88`) and uses it for later phases (contract merge/write/flush), but not for this early state-opening phase.

## Root Cause Hypothesis

The method assumes per-token state creation is effectively all-or-nothing and only guards later failure points. In batched sink execution, that assumption is wrong: failures can occur after partial state creation, requiring explicit rollback/finalization of already-open states.

## Suggested Fix

Wrap the state-opening loop in `try/except`, and on failure:

1. If any states were opened, mark them `FAILED` via `_complete_states_failed(...)` with a phase like `"begin_node_state"`.
2. Re-raise the original exception.

Also add/extend a unit test in sink executor tests to simulate `begin_node_state.side_effect=[state1, Exception(...)]` and assert opened states are completed as `FAILED`.

## Impact

- Breaks audit invariants about terminal state progression.
- Produces orphaned `OPEN` sink states with no corresponding terminal outcome.
- Creates misleading lineage (row appears to have reached sink execution but never finalized), which can impair recovery diagnostics and violate "no silent drops" expectations.
