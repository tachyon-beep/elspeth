# Test Bug Report: Fix weak assertions in orchestrator_telemetry

## Summary

- This test file provides comprehensive coverage of telemetry event emission in the Orchestrator across seven test classes. Tests verify event ordering, content, emission conditions, and integration with the Landscape audit trail. The tests use a clean `RecordingExporter` pattern to capture events for verification. However, some tests make claims about code structure in comments rather than verifying behavior, and there is manual graph construction that bypasses production paths.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_telemetry.py.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_telemetry.py`
- **Lines:** 729
- **Test count:** 16

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests provide valuable coverage of telemetry emission, but the `TestNoTelemetryOnLandscapeFailure` tests should be strengthened to actually test the failure scenarios rather than relying on code structure claims in comments. The manual graph construction is acceptable for unit-style telemetry tests. Consider adding tests that mock Landscape failures to verify telemetry is not emitted.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_telemetry.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_telemetry.py.audit.md`
