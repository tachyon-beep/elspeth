## Summary

`GateExecutor` records gate routing events before the gate has actually committed a successful outcome, so any later failure leaves ghost routes in Landscape that claim an edge was taken when the token never advanced.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/gate.py
- Line(s): 144-149, 163-182, 302-325
- Function/Method: `GateExecutor._dispatch_resolved_destination`, `GateExecutor.execute_config_gate`

## Evidence

`_dispatch_resolved_destination()` persists routing immediately for all successful-looking branches:

```python
# /home/john/elspeth/src/elspeth/engine/executors/gate.py:144-149
self._record_routing(
    state_id=state_id,
    node_id=node_id,
    action=action,
)
return _RouteDispatchOutcome(action=action)
```

The same early write happens for fork and route destinations:

```python
# /home/john/elspeth/src/elspeth/engine/executors/gate.py:163-175
self._record_routing(...)
child_tokens, _fork_group_id = token_manager.fork_token(...)
return _RouteDispatchOutcome(...)
```

But `execute_config_gate()` still has failure points after dispatch returns:

```python
# /home/john/elspeth/src/elspeth/engine/executors/gate.py:304-325
result = GateResult(...)
result.input_hash = input_hash
result.output_hash = stable_hash(input_dict)  # can raise
...
guard.complete(
    NodeStateStatus.COMPLETED,
    output_data=input_dict,
    duration_ms=duration_ms,
    context_after=gate_context,
)
```

The repo already has a regression test proving this post-dispatch failure path is real:

```python
# /home/john/elspeth/tests/unit/engine/test_executors.py:1493-1549
# stable_hash is patched to fail after dispatch
with pytest.raises(ValueError, match="Simulated output hash failure"):
    executor.execute_config_gate(...)
# state becomes FAILED via NodeStateGuard
```

If that exception is raised, `processor.py` never consumes the returned `GateOutcome`, so the token does not advance:

```python
# /home/john/elspeth/src/elspeth/engine/processor.py:1755-1762
outcome = self._gate_executor.execute_config_gate(...)
current_token = outcome.updated_token
```

For fork routes the inconsistency is worse: routing is recorded before child creation, but child-token creation is a separate operation that can still fail:

```python
# /home/john/elspeth/src/elspeth/engine/tokens.py:242-263
children, fork_group_id = self._recorder.fork_token(...)
```

```python
# /home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:468-535
# creates child tokens and parent FORKED outcome atomically, and can raise AuditIntegrityError
```

So `gate.py` can leave a FAILED node_state plus persisted routing_events for branches that were never actually realized.

## Root Cause Hypothesis

`gate.py` treats routing-event insertion as part of “dispatch” instead of part of “committed success.” That ordering means audit side effects are emitted before later hash/completion work has proven the gate execution succeeded. The executor has a guard for terminal node-state closure, but no equivalent guard preventing premature routing persistence.

## Suggested Fix

Defer routing-event persistence until after all later failure points that can still abort gate success.

A practical fix in `gate.py` is to split dispatch into two phases:

1. Resolve destination and create any required child tokens first.
2. Compute hashes/build `GateResult`.
3. Record routing events only once success is about to be committed.
4. Complete the node state immediately after.

For fork destinations specifically, child creation should happen before routing is recorded. If stronger guarantees are needed, introduce an atomic recorder operation for “complete gate state + record routing.”

## Impact

The audit trail can claim that a gate routed a token down an edge even though the gate ultimately failed and the token never moved. That breaks traceability and can mislead `explain()` consumers, operators, or auditors about what actually happened. On fork paths it can also imply child-lineage fan-out that never successfully occurred.
