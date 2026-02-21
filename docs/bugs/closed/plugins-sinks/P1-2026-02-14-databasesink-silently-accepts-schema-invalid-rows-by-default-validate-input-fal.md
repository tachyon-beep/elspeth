## Summary

`DatabaseSink` silently accepts schema-invalid rows by default (`validate_input=False`), which can drop unexpected fields and insert `NULL` for required fields instead of failing fast.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 — real gap but upstream Tier 2 trust model and CSVSink analogy limit blast radius

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/database_sink.py`
- Line(s): `52`, `114-115`, `283-287`, `338-341`, `352`
- Function/Method: `DatabaseSink.write`, `_create_columns_from_schema_or_row`

## Evidence

The sink defaults to no runtime schema validation:

```python
# database_sink.py
validate_input: bool = False
...
if self._validate_input and not self._schema_config.is_observed:
    self._schema_class.model_validate(row)
```

So in default mode, rows go straight to SQLAlchemy insert:

```python
conn.execute(insert(self._table), rows)
```

Two concrete failures follow from this implementation:

1. Required fields are not enforced at DB column level (`Column(..., nullable=True default)`), so missing required fields become `NULL`.
2. Extra keys in row dicts are silently ignored by SQLAlchemy insert for known-table columns, so unexpected data is dropped without error.

This contradicts the file's own claim in fixed mode that extras are "rejected at insert time" (`database_sink.py:114-115`) and violates the trust-model expectation that upstream schema bugs should crash, not be silently absorbed.

## Root Cause Hypothesis

`DatabaseSink` relies on optional validation and assumes SQL insert semantics will enforce strictness. In practice, SQLAlchemy/dialect behavior does not enforce strict schema conformance for dict keys/requiredness unless explicitly validated or constrained.

## Suggested Fix

Always enforce explicit-schema conformance in `DatabaseSink.write()` (at least for `fixed`/`flexible` modes), independent of `validate_input`:

- Validate every row with `self._schema_class.model_validate(row)` in explicit modes.
- Add explicit required-field presence checks (like `CSVSink` does).
- Define DB columns as `nullable=not field_def.required` in `_create_columns_from_schema_or_row`.
- Keep `validate_input` only for observed mode or remove the toggle for this sink.

## Impact

Silent data loss and contract drift in sink outputs:
- Required fields can disappear into `NULL`.
- Unexpected fields can vanish without audit-visible failure.
- Audit trail may show successful sink writes for semantically corrupted output rows.
