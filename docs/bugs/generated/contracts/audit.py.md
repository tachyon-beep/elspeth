## Summary

`ValidationErrorRecord` drops structured schema-violation metadata (`violation_type`, field names, expected/actual types) even though the audit layer persists it, so reading validation errors through the contract API silently strips probative audit data.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/audit.py
- Line(s): 531-547
- Function/Method: `ValidationErrorRecord`

## Evidence

`ValidationErrorRecord` only models the legacy fields:

```python
@dataclass(frozen=True, slots=True)
class ValidationErrorRecord:
    error_id: str
    run_id: str
    node_id: str | None
    row_hash: str
    error: str
    schema_mode: str
    destination: str
    created_at: datetime
    row_data_json: str | None = None
```

Source: `/home/john/elspeth/src/elspeth/contracts/audit.py:531-547`

But the database schema stores additional structured contract-violation columns:

```python
Column("violation_type", String(32)),
Column("original_field_name", String(256)),
Column("normalized_field_name", String(256)),
Column("expected_type", String(32)),
Column("actual_type", String(32)),
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:423-429`

Those fields are actually written on every validation error when a contract violation is available:

```python
validation_errors_table.insert().values(
    ...
    violation_type=violation_type,
    normalized_field_name=normalized_field_name,
    original_field_name=original_field_name,
    expected_type=expected_type,
    actual_type=actual_type,
)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:1316-1332`

The contract loader then throws that data away when reconstructing `ValidationErrorRecord`:

```python
return ValidationErrorRecord(
    error_id=row.error_id,
    run_id=row.run_id,
    node_id=row.node_id,
    row_hash=row.row_hash,
    error=row.error,
    schema_mode=row.schema_mode,
    destination=row.destination,
    created_at=row.created_at,
    row_data_json=row.row_data_json,
)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py:420-430`

This is not dead metadata. Other parts of the system expose these fields as first-class audit data, for example MCP contract-violation reports require them:

Source: `/home/john/elspeth/src/elspeth/mcp/types.py:513-526`

And integration tests verify the DB row contains them after recording:

Source: `/home/john/elspeth/tests/integration/audit/test_contract_audit.py:254-277`

What the code does now: persists structured violation evidence, then loses it on read through the contract model.

What it should do: preserve the full validation-error record in `ValidationErrorRecord` so audit/query APIs can round-trip the evidence without direct SQL access.

## Root Cause Hypothesis

`ValidationErrorRecord` was not updated when contract-audit enrichment was added to `validation_errors`. The schema, writer, and MCP-facing types evolved, but the read-side contract in `contracts/audit.py` remained on the older shape, and the loader followed that stale contract.

## Suggested Fix

Add the missing optional fields to `ValidationErrorRecord` in `/home/john/elspeth/src/elspeth/contracts/audit.py`, for example:

```python
violation_type: str | None = None
original_field_name: str | None = None
normalized_field_name: str | None = None
expected_type: str | None = None
actual_type: str | None = None
```

Then update the loader to populate them and add/extend round-trip tests so `get_validation_errors_for_run()` and `get_validation_errors_for_row()` preserve these fields.

## Impact

Audit consumers that rely on `ValidationErrorRecord` cannot recover which field violated the contract or what the expected vs actual type was, even though the audit trail recorded it. That weakens the “if it’s not recorded, it didn’t happen” standard in practice by making recorded evidence inaccessible through the contract API, and it forces callers to bypass the contract layer with raw SQL to explain quarantined rows.
