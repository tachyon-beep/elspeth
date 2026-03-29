## Summary

`GateOutcome` only checks that `sink_name` and `next_node_id` are not both set, so it accepts impossible routing states that the processor later interprets as real routing decisions; malformed outcomes can misroute a token or mark a fork as successful without creating any child work.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/types.py
- Line(s): 47-54
- Function/Method: `GateOutcome.__post_init__`

## Evidence

`GateOutcome.__post_init__` currently enforces only one invariant:

```python
def __post_init__(self) -> None:
    object.__setattr__(self, "child_tokens", tuple(self.child_tokens))
    if self.sink_name is not None and self.next_node_id is not None:
        raise ValueError(...)
```

There is no check that these fields agree with `result.action.kind`.

That leaves several invalid states constructible:

1. `CONTINUE` action plus `sink_name`:
   - `/home/john/elspeth/tests/unit/engine/test_executors.py:266-278` constructs exactly this and it succeeds:
   ```python
   result = GateResult(row={"a": 1}, action=RoutingAction.continue_())
   outcome = GateOutcome(..., sink_name="error_sink")
   ```
   - The processor treats `sink_name` as authoritative before it checks `action.kind`:
   - `/home/john/elspeth/src/elspeth/engine/processor.py:1775-1792`
   ```python
   if outcome.sink_name is not None:
       current_result = RowResult(..., outcome=RowOutcome.ROUTED, sink_name=outcome.sink_name)
       return _GateTerminal(result=current_result)
   ```
   So an internally contradictory outcome is recorded as `ROUTED`, even though the gate action says `CONTINUE`.

2. `ROUTE` action with neither `sink_name` nor `next_node_id`:
   - `/home/john/elspeth/tests/unit/engine/test_processor.py:2583-2593` constructs this invalid state successfully.
   - The processor only notices later and raises at `/home/john/elspeth/src/elspeth/engine/processor.py:1840-1845`, which means the invariant is enforced too late and outside the type that owns the contract.

3. `FORK_TO_PATHS` action with empty `child_tokens`:
   - `GateOutcome` allows it today because it never checks fork semantics.
   - `_handle_gate_fork()` blindly iterates `outcome.child_tokens` and then returns the parent as `FORKED`:
   - `/home/john/elspeth/src/elspeth/engine/processor.py:1869-1902`
   ```python
   for child_token in outcome.child_tokens:
       ...
   return _GateTerminal(
       result=RowResult(..., outcome=RowOutcome.FORKED)
   )
   ```
   If `child_tokens` is empty, the audit trail can say the token forked, but no branch work is created.

What the code does now:
- Accepts contradictory `GateOutcome` objects.
- Lets downstream code interpret those contradictions differently depending on field precedence.

What it should do:
- Reject impossible gate states at `GateOutcome` construction time, because this is system-owned Tier 1 data and should fail closed immediately.

## Root Cause Hypothesis

`GateOutcome` was treated as a lightweight transport object rather than a contract-enforcing boundary type. Its validation only covers one field-pair conflict, but the real invariant depends on `result.action.kind`:

- `CONTINUE` must not carry `sink_name`, `next_node_id`, or `child_tokens`
- `ROUTE` must carry exactly one of `sink_name` or `next_node_id`
- `FORK_TO_PATHS` must carry non-empty `child_tokens` and no `sink_name`/`next_node_id`

Because that coupling is not enforced in `types.py`, consumers have to infer intent from partially overlapping fields, which creates audit-integrity risk.

## Suggested Fix

Strengthen `GateOutcome.__post_init__` so it validates against `result.action.kind`, not just field exclusivity.

Helpful shape:

```python
def __post_init__(self) -> None:
    object.__setattr__(self, "child_tokens", tuple(self.child_tokens))

    action_kind = self.result.action.kind

    if self.sink_name is not None and self.next_node_id is not None:
        raise ValueError("...")

    if action_kind == RoutingKind.CONTINUE:
        if self.sink_name is not None or self.next_node_id is not None or self.child_tokens:
            raise ValueError("CONTINUE outcome must not include sink_name, next_node_id, or child_tokens")
        return

    if action_kind == RoutingKind.ROUTE:
        if (self.sink_name is None) == (self.next_node_id is None):
            raise ValueError("ROUTE outcome must include exactly one of sink_name or next_node_id")
        if self.child_tokens:
            raise ValueError("ROUTE outcome must not include child_tokens")
        return

    if action_kind == RoutingKind.FORK_TO_PATHS:
        if not self.child_tokens:
            raise ValueError("FORK_TO_PATHS outcome requires child_tokens")
        if self.sink_name is not None or self.next_node_id is not None:
            raise ValueError("FORK_TO_PATHS outcome must not include sink_name or next_node_id")
        return
```

Tests should also be updated so impossible combinations fail at construction, instead of being accepted and only rejected later in `RowProcessor`.

## Impact

Malformed gate outcomes can violate audit guarantees in two ways:

- A gate can be recorded/telemetered as routing to a sink even when its action says `CONTINUE`, creating contradictory internal state.
- A fork outcome can mark the parent token as `FORKED` while producing no child work items, which is silent data loss from the DAG’s perspective.

This breaks the project’s “fail closed” requirement for system-owned data and risks incomplete or contradictory lineage for routed/forked tokens.
