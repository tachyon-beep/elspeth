# Test Audit: tests/integration/test_cli_resume.py

**Auditor:** Claude
**Date:** 2026-02-05
**Lines:** 62
**Batch:** 97

## Summary

This file contains a single integration test for the resume command. It verifies that the resume command uses the new graph construction path and doesn't use deprecated APIs.

## Findings

### 1. CRITICAL: Test That Does Nothing Meaningful

Lines 11-62 contain a test that doesn't actually test resume functionality:

```python
def test_resume_command_uses_new_graph_construction():
    """Verify resume command builds graph from plugin instances."""
    # This test verifies resume doesn't call deprecated from_config()
    # Actual checkpoint/resume testing requires database setup
    ...
    # Resume with non-existent run_id should fail gracefully
    result = runner.invoke(
        app,
        ["resume", "nonexistent-run-id", "--settings", str(config_file)],
    )
    # Should exit with error (run not found), not crash
    assert result.exit_code != 0
    # Should NOT contain deprecation warning
    assert "deprecated" not in result.output.lower()
```

**Problems:**
1. The test only verifies that resuming a non-existent run fails - this is trivial
2. The test never actually tests resume functionality (no checkpoint, no actual recovery)
3. The assertion `assert "deprecated" not in result.output.lower()` is weak - it only checks output text, not actual code path
4. The comment admits "Actual checkpoint/resume testing requires database setup" but doesn't do that setup

**Severity:** HIGH
**Impact:** This test provides false confidence. The resume command could be completely broken and this test would still pass as long as it exits non-zero and doesn't print "deprecated".

### 2. MISSING: No Actual Resume Testing

The file claims to test "resume command with new schema validation" but:
- Never creates a checkpoint
- Never creates a run that could be resumed
- Never verifies actual resume behavior

**Severity:** HIGH
**Recommendation:** Either:
1. Delete this test if resume functionality is tested elsewhere (check `test_checkpoint_recovery.py`)
2. Or implement proper resume testing with:
   - Create a run
   - Process some rows
   - Create checkpoint
   - "Crash" (stop processing)
   - Resume
   - Verify remaining rows processed

### 3. INEFFICIENCY: Manual Config File Creation

Lines 19-42 manually create a YAML config file:
```python
config_yaml = """
source:
  plugin: csv
  ...
"""
with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
    f.write(config_yaml)
```

This could use pytest's `tmp_path` fixture like other tests in this directory.

**Severity:** Low
**Recommendation:** Use `tmp_path` fixture for consistency.

### 4. NO CLASS - Uses Module-Level Function

The test is defined as a module-level function, not in a class:
```python
def test_resume_command_uses_new_graph_construction():
```

This is valid pytest but inconsistent with other tests in this directory which use classes.

**Severity:** Low
**Recommendation:** Consider wrapping in `TestCLIResume` class for consistency.

### 5. CONCERN: Test Name Misleading

The test name is `test_resume_command_uses_new_graph_construction` but the test doesn't actually verify that the new graph construction is used. It only checks that the output doesn't contain "deprecated".

**Severity:** MEDIUM
**Recommendation:** Either rename to reflect what it actually tests, or implement what the name claims.

### 6. POSITIVE: Cleans Up Temp File

Line 62 properly cleans up the temp file:
```python
finally:
    config_file.unlink()
```

## Overall Assessment

**Quality:** LOW

This test is essentially a placeholder. It:
- Doesn't test what its name/docstring claims
- Only verifies a non-existent run fails (trivial)
- Uses weak text-based assertions
- Provides false confidence about resume functionality

## Recommendations

1. **CRITICAL:** Either implement proper resume testing or delete this file and document where resume is actually tested
2. **HIGH:** Review if resume functionality is properly tested anywhere in the test suite
3. **MEDIUM:** If keeping, rename to accurately describe what it tests (e.g., `test_resume_nonexistent_run_fails_gracefully`)
4. **LOW:** Use `tmp_path` fixture instead of manual tempfile handling

## Action Items

- [ ] **PRIORITY 1:** Find or create proper resume integration tests
- [ ] Decide: delete this test or implement properly
- [ ] If keeping, fix the test name to match behavior
- [ ] Consider consolidating with test_checkpoint_recovery.py

## Related Files (Confirmed)

- `tests/integration/test_checkpoint_recovery.py` - Contains checkpoint/recovery logic tests
- `tests/integration/test_resume_comprehensive.py` - **EXISTS** - Contains comprehensive end-to-end resume tests covering:
  - Normal resume with remaining rows (Happy path)
  - Early-exit resume with no remaining rows (Bug #8)
  - Resume with schema type restoration (Bug #4)
  - Resume with real edge IDs (Bug #3)
  - Checkpoint cleanup on completion
- `tests/integration/test_resume_edge_ids.py` - EXISTS - Tests edge ID handling during resume
- `tests/integration/test_resume_schema_required.py` - EXISTS - Tests schema requirements during resume

**Verdict:** Resume functionality IS properly tested elsewhere. This test file (`test_cli_resume.py`) can be deleted or kept as a minimal smoke test. The test name should be changed to reflect its actual purpose (verifying non-existent run fails gracefully).
