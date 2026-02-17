## Summary

`np.datetime64` values can pass schema-contract validation but crash canonical hashing, so valid non-quarantined rows can fail during audit recording.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/canonical.py
- Line(s): 40-120
- Function/Method: `_normalize_value` (via `canonical_json` / `stable_hash`)

## Evidence

`canonical.py` has normalization branches for `np.integer`, `np.floating`, `np.bool_`, `np.ndarray`, `pd.Timestamp`, etc., but no branch for `np.datetime64` (`src/elspeth/core/canonical.py:71-120`).

The contract layer explicitly treats `np.datetime64` as `datetime` (`src/elspeth/contracts/type_normalization.py:84-87`), and schema validation compares against that normalized type (`src/elspeth/contracts/schema_contract.py:271-274`), so rows with `np.datetime64` can be considered valid.

Non-quarantined source rows are hashed/serialized without fallback (`src/elspeth/core/landscape/_token_recording.py:95`, `src/elspeth/core/landscape/_token_recording.py:111`), so this becomes a hard failure, not a quarantine fallback.

Concrete repro from this audit:

```python
row = {"event_time": np.datetime64("2024-01-01")}
contract.validate(row)  # []
stable_hash(row)        # CanonicalizationError: unsupported type: <class 'numpy.datetime64'>
```

## Root Cause Hypothesis

Canonical normalization coverage drifted from contract type normalization. Contracts accept `np.datetime64` as valid datetime-like data, but canonical serialization does not normalize it to a JSON-safe primitive first.

## Suggested Fix

Add explicit `np.datetime64` handling in `_normalize_value` (including `NaT`), converting to deterministic UTC ISO text (aligned with datetime/timestamp policy). Also add tests in `tests/unit/core/test_canonical.py` and property tests for `np.datetime64` and `np.datetime64("NaT")` round-trip hashing behavior.

## Impact

Valid Tier-2 rows can crash during audit hashing/serialization, causing pipeline failure and violating the contract that validated rows should proceed through recording deterministically.
