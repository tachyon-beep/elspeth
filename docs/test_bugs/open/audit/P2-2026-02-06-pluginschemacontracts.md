# Test Bug Report: Fix weak assertions in plugin_schema_contracts

## Summary

- This test file verifies that plugins follow schema initialization contracts, ensuring schemas are set in `__init__()`. The tests are well-structured and follow the codebase's prohibition on defensive patterns (using direct attribute access instead of `hasattr`). However, there are several issues: contradictory use of `hasattr` for behavioral validation despite the file's stated prohibition, tests that always skip providing no value, missing plugins in the skip list that are defined in configs, and some weak validation patterns.

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_audit_test_plugin_schema_contracts.py.audit.md

## Test File

- **File:** `tests/audit/test_plugin_schema_contracts.py`
- **Lines:** 461
- **Test count:** 17

## Findings

- **Lines 187-188, 268-269, 351:**: Contradictory `hasattr()` usage. The file header explicitly states it uses "direct attribute access (not hasattr) per CLAUDE.md prohibition on defensive patterns" (line 6-8), yet these lines use `hasattr(schema, "model_validate")` for validation. If the schema is a proper PluginSchema subclass, direct access to `model_validate` should be used. If it's the wrong type, direct access would raise `AttributeError` which is the desired behavior per CLAUDE.md. This is inconsistent with the file's stated philosophy.
- **Lines 200-206, 287-293, 363-369:**: Tests that only call `pytest.skip()` provide no actual test coverage. While they document which plugins require credentials, they inflate test count without testing anything. These could be removed and replaced with comments in the config dicts themselves. The skip tests always skip unconditionally - they are effectively no-ops.
- **Lines 103-105:**: `TRANSFORM_CONFIGS` includes `"openrouter_batch_llm": None` but there is no corresponding entry in the skip test at lines 275-285. This means if `openrouter_batch_llm` is registered, `test_all_transforms_have_explicit_config` would pass but there would be no skip test documenting why it's skipped. Inconsistent documentation.
- **Lines 192, 272-273, 354, 404, 423, 443, 461:**: The schema validation calls like `schema.model_validate({"test_field": "test_value"})` don't actually assert anything about the result. They verify the method doesn't throw, but don't verify the returned validated object is correct. This is weak validation - the schema could accept the input but produce garbage output.
- **Lines 380-404, 406-423, 425-443, 445-461:**: The `TestPluginInitSafety` tests duplicate the `PluginManager` setup in each test method rather than using a shared fixture like the other test classes. This is inefficient and inconsistent with the pattern established in the other test classes.
- **Lines 150-154, 229-233, 316-319:**: The `test_all_*_have_explicit_config` tests are good defensive tests that ensure new plugins aren't silently untested. This is a valuable pattern.
- **Lines 145-155, 224-234, 311-320:**: These tests iterate over `manager.get_*()` but don't verify the iteration itself works correctly - if `get_sources()`, `get_transforms()`, or `get_sinks()` returns an empty list due to a bug, the tests would pass vacuously (no iterations = no failures).
- **Lines 112-127:**: `SINK_CONFIGS` embeds `test_row` in the config dict alongside actual config keys, then extracts it at line 338. This is a slightly awkward pattern - having test data mixed with config data. A separate `SINK_TEST_ROWS` dict would be cleaner.
- **Lines 170, 249, 335:**: The `assert config is not None` assertions are redundant because the parametrize decorator already filters to configs where `cfg is not None`. These don't hurt but are unnecessary.


## Verdict Detail

**KEEP** - The tests provide valuable coverage of a critical architectural contract (schemas must be set in `__init__`). The issues identified are relatively minor: some inconsistency with `hasattr` usage, skip tests that could be documentation instead, and some weak validation patterns. The core logic is sound and the parameterized approach ensures new plugins are not silently missed. The structural issues don't undermine the test's ability to catch real bugs.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/audit/test_plugin_schema_contracts.py -v`

## Notes

- Source audit: `docs/test_audit/tests_audit_test_plugin_schema_contracts.py.audit.md`
