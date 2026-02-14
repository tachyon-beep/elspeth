## Summary

`DROP TABLE`/`CREATE TABLE` SQL calls are executed without `ctx.record_call` instrumentation, so failures in those paths lose call-level audit context.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/database_sink.py`
- Line(s): `231`, `243`, `257-263`, `348-383`
- Function/Method: `_ensure_table`, `_drop_table_if_exists`, `write`

## Evidence

DDL operations occur before the only call-recording try/except block:

- `_drop_table_if_exists()` is invoked at `database_sink.py:231`.
- `self._metadata.create_all(...)` executes at `database_sink.py:243`.
- `ctx.record_call(...)` exists only inside the insert block starting at `database_sink.py:348`.

So if drop/create fails, `write()` raises without recording a SQL call entry for that failure path (only operation-level failure is available upstream).

## Root Cause Hypothesis

Call-level audit recording was implemented only for `INSERT`, but table lifecycle SQL (`DROP`/`CREATE`) was left outside the same instrumentation boundary.

## Suggested Fix

Instrument DDL operations similarly to insert:

- Wrap drop/create in try/except.
- Record `ctx.record_call(call_type=CallType.SQL, ...)` with `operation` values like `DROP_TABLE` and `CREATE_TABLE`.
- Include table name, mode (`if_exists`), and error details on failure.

## Impact

Audit and observability blind spot for schema-management SQL:
- Harder to explain failures in replace/initialization paths.
- Missing call-level lineage for external DB actions preceding inserts.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/sinks/database_sink.py.md`
- Finding index in source report: 3
- Beads: pending
