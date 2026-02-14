## Summary

Non-finite numeric values can bypass source-boundary validation in `schema_factory.py` (notably for explicit `any` fields), then crash later during canonical hashing instead of being quarantined.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/schema_factory.py`
- Line(s): `33-39`, `77-84`, `115-120`, `170-179`, `42-66`
- Function/Method: `create_schema_from_config`, `_create_explicit_schema`, `_find_non_finite_value_path`

## Evidence

`schema_factory.py` only applies the non-finite validator in observed mode:

- `/home/john/elspeth-rapid/src/elspeth/plugins/schema_factory.py:115-120` routes observed mode to `_create_dynamic_schema`, but explicit modes to `_create_explicit_schema`.
- `/home/john/elspeth-rapid/src/elspeth/plugins/schema_factory.py:128-136` uses `__base__=_ObservedPluginSchema` (has non-finite validator).
- `/home/john/elspeth-rapid/src/elspeth/plugins/schema_factory.py:170-179` uses `__base__=PluginSchema` (no non-finite validator).
- `/home/john/elspeth-rapid/src/elspeth/plugins/schema_factory.py:33-39` maps `"any"` to `Any`, so explicit `any` fields accept `inf`/`nan`.

JSON source can produce `inf` from overflow numeric literals (`1e309`) even with `parse_constant`:

- `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:210` and `:245` use `json.loads/json.load(..., parse_constant=...)`, which only handles `NaN/Infinity` tokens, not overflow finite literals.
- `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:341-374` validates and yields as valid row when schema accepts it.

Later, non-quarantined rows are hashed and crash:

- `/home/john/elspeth-rapid/src/elspeth/engine/tokens.py:107-112` calls `create_row(..., quarantined=False)`.
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:95` calls `stable_hash(data)` for non-quarantined rows.
- `/home/john/elspeth-rapid/src/elspeth/core/canonical.py:59-63` raises on non-finite float.

Repro run in this workspace:

- `json.loads('{"value": 1e309}')` produced `{'value': inf}`
- `create_schema_from_config(... fields=['value: any'])` accepted it
- `stable_hash(...)` failed with `ValueError: Cannot canonicalize non-finite float: inf`

## Root Cause Hypothesis

Non-finite enforcement is scoped to observed schemas (and float-specific annotations), but explicit schemas with `any` bypass that guard. This creates a gap between source validation and canonicalization guarantees, especially for JSON numeric overflow (`1e309 -> inf`).

## Suggested Fix

In `schema_factory.py`, enforce non-finite rejection at source boundary for **all** schema modes when `allow_coercion=True` (not just observed), including `any` fields.

Implementation direction:

- Introduce a shared base validator for source-boundary non-finite checks.
- Use that base in both `_create_dynamic_schema` and `_create_explicit_schema` when `allow_coercion=True`.
- Extend `_find_non_finite_value_path` to also reject non-finite `Decimal` values.
- Add regression tests:
  - explicit `fixed/flexible` schema with `any` rejects `inf/nan`
  - JSON source row with `1e309` is quarantined (not run-crashing)

## Impact

- Tier-3 malformed rows can pass source validation and crash during audit hashing.
- Violates the trust model requirement to quarantine bad external rows at the boundary.
- Can abort runs mid-processing and prevent rows from reaching normal terminal outcomes, reducing audit reliability.
