# Test Audit: tests/integration/test_cli_integration.py

**Auditor:** Claude
**Date:** 2026-02-05
**Lines:** 246
**Batch:** 97

## Summary

This file contains end-to-end CLI integration tests. It verifies the full workflow from configuration validation through pipeline execution to output verification. This is one of the most important test files as it exercises the production code path.

## Findings

### 1. STRENGTH: Tests Production Code Path

These tests use the CLI runner to invoke actual CLI commands, which exercises the full production code path:

```python
result = runner.invoke(app, ["run", "-s", str(pipeline_config), "--execute"])
```

This is the correct approach for integration tests - it goes through config loading, plugin instantiation, orchestration, and output.

**Verdict:** Excellent test path integrity.

### 2. STRENGTH: Tests Quarantine Routing Feature

Lines 121-246 test the source quarantine routing feature, which is critical for audit compliance. The test verifies:
- Invalid rows are routed to quarantine sink
- Valid rows go to default output
- `on_validation_failure=discard` silently drops invalid rows

**Verdict:** Important acceptance test for a key feature.

### 3. MINOR: Test Relies on CliRunner Output Parsing

Lines 66-67 and 72 parse CLI output:
```python
assert "valid" in result.stdout.lower()
assert "completed" in result.stdout.lower()
```

These assertions are fragile if output wording changes. However, for integration tests this is acceptable since the output format is part of the user contract.

**Severity:** Low
**Recommendation:** Consider using structured exit codes or output files rather than text parsing where possible.

### 4. STRENGTH: Tests Dry-Run Safety

Lines 96-107 verify that `--dry-run` doesn't create output files:
```python
def test_dry_run_does_not_create_output(self, pipeline_config: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "-s", str(pipeline_config), "--dry-run"])
    assert result.exit_code == 0
    assert not output_file.exists()
```

This is an important safety test.

### 5. STRENGTH: Tests Execute Flag Requirement

Lines 109-118 verify the safety feature requiring `--execute` flag:
```python
def test_run_without_flags_exits_with_warning(self, pipeline_config: Path) -> None:
    result = runner.invoke(app, ["run", "-s", str(pipeline_config)])
    assert result.exit_code == 1
    assert "--execute" in result.output
```

This verifies the safety mechanism that prevents accidental execution.

### 6. POTENTIAL ISSUE: Hardcoded Sink Name "default"

The test configuration uses "default" as the sink name (lines 44-49), and the docstring notes this is required:
```python
# "default" is required - Orchestrator routes completed rows here
"default": {
    "plugin": "json",
    ...
}
```

If the orchestrator's default sink naming changes, this test would fail with a confusing error.

**Severity:** Low
**Recommendation:** The comment is helpful. Consider adding an assertion that validates the orchestrator's expected behavior.

### 7. STRENGTH: Uses tmp_path Fixture

All tests use pytest's `tmp_path` fixture for output files, preventing test pollution:
```python
"landscape": {"url": f"sqlite:///{tmp_path / 'landscape.db'}"}
```

### 8. MISSING COVERAGE: No Transform Tests

The CLI integration tests only cover source -> sink pipelines. There's no test with transforms in the middle.

**Severity:** MEDIUM
**Recommendation:** Add a test that includes at least one transform to verify the full DAG execution path.

### 9. NO CLASS DISCOVERY ISSUES

All test classes have the `Test` prefix:
- `TestCLIIntegration`
- `TestSourceQuarantineRouting`

**Verdict:** All classes will be discovered by pytest.

### 10. NO TEST PATH INTEGRITY VIOLATIONS

These tests use the CLI which invokes `from_plugin_instances()` internally. This is the correct production path.

## Overall Assessment

**Quality:** HIGH

This is an excellent integration test file that exercises the production CLI code path. The tests verify:
- Full workflow (validate -> run -> check output)
- Plugin listing
- Dry-run safety
- Execute flag requirement
- Source quarantine routing

The tests correctly use the CLI runner rather than directly instantiating internal components.

## Recommendations

1. **MEDIUM:** Add a test that includes transforms to verify full DAG execution
2. **LOW:** Consider testing error scenarios (missing config file, invalid plugin name)
3. **LOW:** Consider adding test for `resume` command with real checkpoint

## Action Items

- [ ] Add test with at least one transform in pipeline
- [ ] Consider adding negative test cases
- [ ] Review if all important CLI commands have test coverage
