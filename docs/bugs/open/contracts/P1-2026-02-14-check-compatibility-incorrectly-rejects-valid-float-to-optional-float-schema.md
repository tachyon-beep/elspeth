## Summary

`check_compatibility()` incorrectly rejects valid `float -> Optional[float]` schema edges when the optional float comes from config-generated schemas, because `_types_compatible()` does not unwrap `typing.Annotated` metadata.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/data.py`
- Line(s): `179-183`, `235-279`
- Function/Method: `check_compatibility`, `_types_compatible`

## Evidence

`check_compatibility()` compares raw field annotations (`producer_field.annotation`, `consumer_field.annotation`) via `_types_compatible()` at `src/elspeth/contracts/data.py:179-183`.

`_types_compatible()` in `src/elspeth/contracts/data.py:235-279` handles exact types, `Any`, numeric `int->float`, and `Union`, but never unwraps `typing.Annotated`.

Config-generated optional float fields become `Optional[Annotated[float, ...]]` (from `FiniteFloat | None`):
- `src/elspeth/plugins/schema_factory.py:29`
- `src/elspeth/plugins/schema_factory.py:33-37`
- `src/elspeth/plugins/schema_factory.py:194-196`

So for:
- producer annotation: `float`
- consumer annotation: `Optional[Annotated[float, ...]]`

`_types_compatible(float, Annotated[float, ...])` returns `False`, causing a false type mismatch.

Reproduction output (executed in repo):
- producer annotation: `<class 'float'>`
- consumer annotation: `typing.Optional[typing.Annotated[float, FieldInfo(...allow_inf_nan=False...)]]`
- `compatible: False`
- `error: Type mismatches: score (... expected Optional[Annotated[float,...]], got float)`

This bubbles up to DAG edge validation failure:
- `src/elspeth/core/dag/graph.py:1040-1046` (`GraphValidationError` raised from `check_compatibility` result)

What code does now: rejects a valid producer/consumer pair.
What it should do: treat `Annotated[T, ...]` as `T` for compatibility checks and accept `float -> Optional[float]`.

## Root Cause Hypothesis

`data.py`'s compatibility logic predates/omits handling for constrained `Annotated` types introduced by schema factory float handling (`FiniteFloat`). The algorithm compares annotation wrappers literally instead of normalizing to semantic base types before union/member checks.

## Suggested Fix

In `src/elspeth/contracts/data.py`, normalize annotations before comparison:

1. Add an `_unwrap_annotated()` helper (similar to `src/elspeth/contracts/transform_contract.py:25-33`).
2. In `_types_compatible()`, unwrap both `actual` and `expected` at function start (and/or before recursive union member checks).
3. Keep existing strict/coercion logic after normalization.

Also add a regression test in compatibility/edge-validation tests for:
- producer required `float`
- consumer optional `float?` from `create_schema_from_config(...)`
- expected result: compatible.

## Impact

Valid pipelines with config-defined optional float fields can fail graph construction with false schema incompatibility errors. This is a contract-validation false negative that blocks execution and can incorrectly signal upstream plugin/schema bugs where none exist.
