## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/infrastructure/sentinels.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/sentinels.py
- Line(s): 33-64
- Function/Method: `MissingSentinel.__new__`, `MissingSentinel.__copy__`, `MissingSentinel.__deepcopy__`, `MissingSentinel.__reduce__`

## Evidence

`MISSING` is implemented as a process-local singleton in [src/elspeth/plugins/infrastructure/sentinels.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/sentinels.py#L33), with identity-preserving copy/deepcopy/pickle hooks at [src/elspeth/plugins/infrastructure/sentinels.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/sentinels.py#L46) and [src/elspeth/plugins/infrastructure/sentinels.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/sentinels.py#L57).

Callers rely on identity comparison rather than equality:
- [src/elspeth/plugins/infrastructure/utils.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/utils.py#L12) returns `MISSING` for absent nested paths.
- [src/elspeth/plugins/transforms/field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L133) branches on `if value is MISSING:`.

Existing tests cover the main behavioral contract:
- [tests/unit/plugins/test_utils.py](/home/john/elspeth/tests/unit/plugins/test_utils.py#L31) verifies missing-path lookups return the sentinel and that explicit `None` is not treated as missing.
- Runtime verification confirmed:
  - `MISSING is MissingSentinel()`
  - `MISSING is copy.copy(MISSING)`
  - `MISSING is copy.deepcopy(MISSING)`
  - `MISSING is pickle.loads(pickle.dumps(MISSING))`

What the code does matches what it should do for current integration points: it preserves a distinct, identity-stable sentinel for “missing field” without conflating that state with `None`.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix recommended.

## Impact

No confirmed breakage in the target file. Current callers retain the required semantic distinction between “field absent” and “field present with `None`,” and I did not find an audit, contract, state-management, or integration failure whose primary fix belongs in `sentinels.py`.
