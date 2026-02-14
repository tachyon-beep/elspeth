## Summary

`create_contract_from_config()` can build an internally inconsistent contract (`mode="FIXED"` with `locked=False`) because lock state is derived from raw `config.mode` while mode is separately normalized.

## Severity

- Severity: major
- Priority: P1 (upgraded from P2 — a FIXED contract that starts unlocked is a silent enforcement failure that undermines schema strictness guarantees)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/schema_contract_factory.py`
- Line(s): 64, 93
- Function/Method: `create_contract_from_config` (and `map_schema_mode` at line 27)

## Evidence

In `schema_contract_factory.py`, mode is normalized first:

```python
mode = map_schema_mode(config.mode)  # line 64
```

but lock state is computed from the unnormalized raw value:

```python
locked = config.mode == "fixed"  # line 93
```

So non-canonical but accepted runtime values can produce invalid state. Repro (executed):

- Input: `SchemaConfig(mode="FIXED", fields=(...))`
- Output contract: `mode="FIXED", locked=False`

That violates the documented invariant (“FIXED schemas start locked”) and allows FIXED behavior to degrade (first-row inference path can activate because contract appears unlocked).

Related gap: there is no runtime guard in this factory for malformed explicit configs (`mode` fixed/flexible with `fields=None`), so invalid contracts can be built instead of failing fast.

Test gap: `tests/unit/contracts/test_schema_contract_factory.py` only validates lowercase canonical modes (`fixed/flexible/observed`) and does not cover this non-canonical-path inconsistency.

## Root Cause Hypothesis

The factory assumes callers always provide canonical, prevalidated `SchemaConfig` values, but it both normalizes mode and separately re-reads raw mode for lock derivation. That split creates inconsistent behavior when input is non-canonical.

## Suggested Fix

In `create_contract_from_config()`:

1. Derive `locked` from normalized `mode`, not raw `config.mode`.
2. Add explicit invariant checks:
1. Reject unknown/non-canonical modes.
2. Reject `mode in {"fixed","flexible"}` when `fields is None`.

Example:

```python
mode = map_schema_mode(config.mode)
if mode not in ("FIXED", "FLEXIBLE", "OBSERVED"):
    raise ValueError(f"Invalid schema mode: {config.mode}")

if mode in ("FIXED", "FLEXIBLE") and config.fields is None:
    raise ValueError(f"{config.mode} mode requires explicit fields")

locked = mode == "FIXED"
```

## Impact

If triggered, schema enforcement can silently diverge from contract intent:

- FIXED contracts may not start locked (contract/protocol violation).
- First-row inference path can run under FIXED mode, weakening strictness.
- Audit guarantees become less reliable because recorded contract mode and runtime lock behavior can disagree.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/schema_contract_factory.py.md`
- Finding index in source report: 1
- Beads: pending
