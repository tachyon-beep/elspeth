## Summary

`SchemaContract.with_field()` crashes on nested JSON values (`dict`/`list`) during observed/flexible inference.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/contracts/schema_contract.py`
- Function/Method: `SchemaContract.with_field`

## Evidence

- Source report: `docs/bugs/generated/contracts/schema_contract.py.md`
- Inference path calls `normalize_type_for_contract(value)` without nested JSON fallback.

## Root Cause Hypothesis

Type inference assumes only primitive values during dynamic source inference.

## Suggested Fix

Handle nested JSON values explicitly as `object` in inference path.

## Impact

Valid source rows can crash ingestion instead of progressing through normal handling.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/schema_contract.py.md`
- Beads: elspeth-rapid-r042
