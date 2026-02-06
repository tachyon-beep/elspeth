# Test Bug Report: Fix weak assertions in cli_helpers

## Summary

- This test file covers the `instantiate_plugins_from_config` helper function with good focus on both happy path and error cases. The tests verify plugin instantiation, schema propagation, and aggregation validation. However, one test has a problematic mocking pattern that could allow bugs to slip through.

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_cli_test_cli_helpers.py.audit.md

## Test File

- **File:** `tests/cli/test_cli_helpers.py`
- **Lines:** 241
- **Test count:** 5

## Findings

- **Line 203-241:**: `test_aggregation_rejects_transform_without_is_batch_aware_attribute` uses extensive mocking that bypasses real plugin instantiation. The mock setup at lines 217-225 creates a `MagicMock` for the transform and patches `_get_plugin_manager`, which means: 1. The test never validates that real plugins behave correctly 2. The mock is patching `elspeth.cli._get_plugin_manager` but `instantiate_plugins_from_config` is imported from `elspeth.cli_helpers`, so the patch location may be incorrect 3. The mocks for source/sink (`MagicMock(return_value=MagicMock())`) are overly permissive and don't verify actual behavior
- **Line 237:**: The patch targets `elspeth.cli._get_plugin_manager` but the function under test `instantiate_plugins_from_config` is from `elspeth.cli_helpers`. If the helper imports the plugin manager differently, this patch may not work as intended.
- **Line 12-77:**: `test_instantiate_plugins_from_config` is thorough - it verifies structure, types, schema presence, plugin identity, and config propagation. Good comprehensive coverage of the happy path.
- **Line 60-62:**: The "CRITICAL: Verify schemas NOT None" comment and corresponding assertions are good defensive checks that document an important invariant.
- **Line 64-67:**: Plugin identity verification (checking `.name` attribute) ensures plugins are actually the right type, not just duck-typed imposters. Good practice.
- **Line 69-76:**: Config propagation verification ensures options flow through to instantiated plugins. This catches bugs where config is lost during instantiation.
- **Line 79-96:**: `test_instantiate_plugins_raises_on_invalid_plugin` uses `TypeAdapter` directly rather than file-based config, which is a valid unit-test approach for error handling.
- **Line 99-150:**: `test_aggregation_rejects_non_batch_aware_transform` is well-structured and tests real behavior with actual plugins (passthrough). The error message assertions (lines 146-149) verify helpful error messages.
- **Line 152-200:**: `test_aggregation_accepts_batch_aware_transform` is the positive counterpart that verifies batch_stats works. Good to have both positive and negative test cases.


## Verdict Detail

**KEEP** - The test file has good coverage of the `instantiate_plugins_from_config` helper. The main concern is the mocking approach in the last test which may not correctly test the intended behavior. The first four tests are solid and provide real value. Consider reviewing whether the patching in `test_aggregation_rejects_transform_without_is_batch_aware_attribute` actually intercepts the correct call path.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/cli/test_cli_helpers.py -v`

## Notes

- Source audit: `docs/test_audit/tests_cli_test_cli_helpers.py.audit.md`
