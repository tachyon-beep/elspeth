## Summary

`PipelineRow.__init__` silently coerces non-dict input via `dict(data)`, masking Tier-1 corruption instead of crashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/schema_contract.py
- Line(s): 525
- Function/Method: `PipelineRow.__init__`

## Evidence

Constructor currently does coercive conversion:

```python
self._data = types.MappingProxyType(dict(data))
```

This accepts non-dict inputs (e.g., iterable key/value pairs) and silently normalizes them.

Direct reproduction from this repo environment:
- `PipelineRow([("a", 1)], contract)` succeeds and produces `{"a": 1}`.

This is risky on Tier-1 restore paths where row payloads are our data and must fail hard on anomalies:
- `src/elspeth/engine/executors/aggregation.py:775-777` restores `PipelineRow(t["row_data"], restored_contract)` from checkpoint token data.
- `src/elspeth/engine/orchestrator/core.py:2211-2213` restores `PipelineRow(data=row_data, contract=schema_contract)` during resume.

What it does now: silently coerces malformed structure.
What it should do: require exact expected type and crash on mismatch.

## Root Cause Hypothesis

Immutability copy logic (`dict(data)`) was implemented as a convenience, but it unintentionally performs schema coercion at an internal trust tier where coercion is forbidden.

## Suggested Fix

In `PipelineRow.__init__`:
- Enforce strict type (`type(data) is dict`), else raise `TypeError` with context.
- Use non-coercive copy (`data.copy()`) before wrapping in `MappingProxyType`.

Optionally, add a test asserting non-dict constructor input raises.

## Impact

- Corrupted/tampered internal row payloads can be normalized into valid-looking rows.
- Violates Tier-1 "crash on anomaly" policy and weakens audit integrity guarantees.
