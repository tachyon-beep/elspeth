## Summary

`BatchReplicate` accepts `bool` in `copies_field` as a valid integer copy count, silently violating the transform's own "must be int" contract and masking upstream type bugs.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 — True=1 is numerically correct, False is caught by quarantine; Tier 2 upstream bug indicator

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_replicate.py`
- Line(s): `155-159`
- Function/Method: `BatchReplicate.process`

## Evidence

`batch_replicate.py` currently checks type with `isinstance(raw_copies, int)`:

```python
if not isinstance(raw_copies, int):
    raise TypeError(...)
```

Because Python `bool` is a subclass of `int`, `True`/`False` pass this check and are treated as `1`/`0`.

- Target file: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_replicate.py:155`
- Type system distinction (bool vs int is explicit in contracts): `/home/john/elspeth-rapid/src/elspeth/contracts/type_normalization.py:24-29`, `/home/john/elspeth-rapid/src/elspeth/contracts/type_normalization.py:93-100`

Runtime verification:

- Input row: `{"id": 1, "copies": True}`
- Observed result: `status=success`, `rows=1`, output includes `copies: True` (no TypeError raised)

So the code does not enforce the documented strict int contract in practice.

## Root Cause Hypothesis

The check uses Python subclass semantics (`isinstance`) rather than exact type semantics for a contract field where `bool` should be rejected as a distinct logical type.

## Suggested Fix

Use exact type checking for this field:

```python
if type(raw_copies) is not int:
    raise TypeError(...)
```

Also add a regression test in `tests/unit/plugins/transforms/test_batch_replicate.py` for `copies=True` and `copies=False` expecting `TypeError`.

## Impact

Wrong-typed pipeline data is silently accepted instead of failing fast. That can produce incorrect replication behavior and hide upstream schema/validation bugs, reducing audit trustworthiness.
