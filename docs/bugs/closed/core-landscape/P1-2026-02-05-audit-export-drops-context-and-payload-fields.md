# BUG #9: Audit Export Drops Context and Payload Fields

**Issue ID:** elspeth-rapid-0511
**Priority:** P1
**Status:** CLOSED
**Date Opened:** 2026-02-05
**Date Closed:** 2026-02-05
**Component:** core-landscape (exporter.py)

## Summary

The `LandscapeExporter` omitted critical fields when converting database records to export format (JSON/CSV). This made exported audit trails incomplete - they couldn't fully investigate failures, reproduce processing decisions, or access payload data.

**Missing fields across four record types:**
1. **node_state**: context_before_json, context_after_json, error_json, success_reason_json
2. **operations**: input_data_ref, output_data_ref
3. **calls**: request_ref, response_ref, error_json, created_at
4. **routing_events**: reason_ref, created_at

## Impact

- **Severity:** High - Audit trail completeness
- **Effect:** Exported audit trails missing critical investigation data
- **Risk:** Can't fully reproduce processing or investigate failures from exports alone

## Root Cause

The exporter was created before several audit trail enhancements were added. As new fields were added to schema tables (context fields, payload references, timestamps), the exporter wasn't updated to include them in exports.

**The gap pattern:**
- Schema has the fields ✓
- Database stores them correctly ✓
- Exporter omits them from export dictionaries ❌

This created a **silent data loss** during export - the audit trail database was complete, but exports were incomplete.

## Files Affected

- `src/elspeth/core/landscape/exporter.py` (lines 337-430)

## Fix

Added all missing fields to export dictionaries for each record type:

**node_state exports (lines 337-417):**
```python
# Added to all four state types (OPEN, PENDING, COMPLETED, FAILED)
"context_before_json": state.context_before_json,
"context_after_json": state.context_after_json,  # or None for OPEN/PENDING
"error_json": state.error_json,  # or None for non-FAILED
"success_reason_json": state.success_reason_json,  # or None for non-COMPLETED
```

**operations exports (lines 233-248):**
```python
"input_data_ref": operation.input_data_ref,
"output_data_ref": operation.output_data_ref,
```

**calls exports (lines 249-263, 433-447):**
```python
"request_ref": call.request_ref,
"response_ref": call.response_ref,
"error_json": call.error_json,
"created_at": call.created_at.isoformat() if call.created_at else None,
```

**routing_events exports (lines 418-430):**
```python
"reason_ref": event.reason_ref,
"created_at": event.created_at.isoformat() if event.created_at else None,
```

## Test Coverage

Added comprehensive test class `TestLandscapeExporterCompleteness` with 4 tests:

1. `test_exporter_includes_node_state_context_fields` - Verifies all context/error/success fields exported
2. `test_exporter_includes_operation_payload_refs` - Verifies input/output_data_ref exported
3. `test_exporter_includes_call_payload_refs_and_timestamps` - Verifies request/response_ref, error, timestamp exported
4. `test_exporter_includes_routing_event_payload_refs` - Verifies reason_ref and timestamp exported

**Test strategy:**
- Create complete audit records with all fields populated
- Export the run
- Verify all expected fields present in export dictionaries
- Verify field values are correct (not NULL when they should have data)

**Test results:**
- RED: All 4 tests failed initially (fields missing from exports)
- GREEN: All 4 tests passed after fix (all fields present)
- All 35 exporter tests pass

## Verification

```bash
# Run new tests
.venv/bin/python -m pytest tests/core/landscape/test_exporter.py::TestLandscapeExporterCompleteness -v

# Run all exporter tests
.venv/bin/python -m pytest tests/core/landscape/test_exporter.py -x
```

**Results:** All 35 tests pass

## Why This Matters

**Scenario: Investigating a production failure**

**Before fix:**
1. Pipeline fails with cryptic error
2. Export audit trail to investigate
3. Export missing error_json - can't see failure details
4. Export missing context_before_json - can't see plugin state
5. Export missing payload refs - can't retrieve full request/response data
6. Investigation stalled - must access production database directly

**After fix:**
1. Pipeline fails with cryptic error
2. Export audit trail to investigate
3. Export includes error_json with full stack trace
4. Export includes context showing plugin checkpoint state
5. Export includes payload refs to retrieve full request/response
6. Investigation complete from export alone - no production database access needed

## Pattern Observed

This is the sixth instance of field mapping gaps:
1. Bug #3 (database_ops) - missing rowcount validation
2. Bug #5 (payload_store) - missing file integrity check
3. Bug #6 (nodestate validation) - missing forbidden field checks
4. Bug #8 (schema validation) - missing Phase 5 columns
5. Bug #10 (operations) - missing BaseException handling
6. **Bug #9 (this bug)** - missing export field mappings

**Lesson:** When schema tables gain new fields, update ALL consumers:
1. Database schema (schema.py) ✓
2. Repository loaders (repositories.py) ✓
3. Recorder methods (recorder.py) ✓
4. **Exporters (exporter.py)** ← Often forgotten!

## Field Reference

For future schema changes, here's the complete field list per record type:

### node_state

| Field | OPEN | PENDING | COMPLETED | FAILED |
|-------|------|---------|-----------|--------|
| context_before_json | ✓ | ✓ | ✓ | ✓ |
| context_after_json | - | ✓ | ✓ | ✓ |
| error_json | - | - | - | ✓ |
| success_reason_json | - | - | ✓ | - |

### operations

- input_data_ref (payload reference for operation input)
- output_data_ref (payload reference for operation output)

### calls

- request_ref (payload reference for call request)
- response_ref (payload reference for call response)
- error_json (error details if call failed)
- created_at (call timestamp)

### routing_events

- reason_ref (payload reference for routing decision details)
- created_at (event timestamp)

## TDD Cycle Duration

- RED (write failing tests): 8 minutes
- GREEN (implement fix): 6 minutes
- Verification (run all tests): 2 minutes
- **Total:** ~16 minutes

## Related Bugs

- Part of Group 1: Tier-1 Audit Trail Integrity (10 bugs total)
- Follows same pattern as Bugs #1-10 (completeness gaps in audit code)
