## Summary

`DatabaseSink` defaults to accepting schema-invalid rows (`validate_input=False`), allowing missing required fields and silent field drops.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/plugins/sinks/database_sink.py`
- Function/Method: `DatabaseSink.write`, `_create_columns_from_schema_or_row`

## Evidence

- Source report: `docs/bugs/generated/plugins/sinks/database_sink.py.md`
- Rows can reach insert path without strict runtime validation in explicit-schema modes.

## Root Cause Hypothesis

Validation was made optional and DB insert semantics were assumed to be strict.

## Suggested Fix

Always enforce explicit-schema validation and required-field checks in explicit modes.

## Impact

Sink writes can succeed with semantically broken data.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/sinks/database_sink.py.md`
- Beads: elspeth-rapid-u16i
