## Summary

JSON structure errors are recorded with `schema_mode="structure"`, which violates the documented schema-mode contract (`fixed|flexible|observed|parse`).

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py
- Line(s): 599, 637, 641, 647
- Function/Method: `AzureBlobSource._load_json_array`

## Evidence

`_load_json_array()` emits:

```python
yield from _record_file_level_error(error_msg, "structure")
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:637`, `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:641`, `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:647`

But contract/docs indicate allowed values are `fixed`, `flexible`, `observed`, `parse`:

- `/home/john/elspeth-rapid/src/elspeth/contracts/plugin_context.py:405`
- `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:478`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py:411`

Related integration expectation also uses `parse` for structural boundary errors:
- `/home/john/elspeth-rapid/tests/integration/plugins/sources/test_trust_boundary.py:704`

What it does now: writes a non-canonical mode label.
What it should do: use the canonical parse-level mode for file/structure boundary errors.

## Root Cause Hypothesis

A local categorization label (`"structure"`) was introduced in this source but not aligned with the shared audit schema contract.

## Suggested Fix

Change structure-path calls to use `"parse"`:

```python
yield from _record_file_level_error(error_msg, "parse")
```

## Impact

Audit records become semantically inconsistent across sources, and downstream reports/queries that rely on canonical `schema_mode` values can undercount/misclassify these failures.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/azure/blob_source.py.md`
- Finding index in source report: 2
- Beads: pending
