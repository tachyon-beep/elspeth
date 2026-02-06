# Test Audit: test_landscape_export.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_landscape_export.py`
**Lines:** 436
**Batch:** 100-101

## Summary

End-to-end integration tests for Landscape audit trail export functionality, including signed export determinism verification.

## Audit Findings

### 1. GOOD: Excellent Determinism Testing

**Location:** `TestSignedExportDeterminism`

The test `test_signed_export_produces_identical_final_hash` is well-designed:
- Creates a run with multiple record types (nodes, edges, rows, tokens, states)
- Exports the SAME run twice
- Verifies both exports produce identical final hash

This is critical for audit integrity.

### 2. DEFECT: Potential Race Condition in CLI Tests

**Severity:** Medium
**Location:** Lines 351-356, 424-429

Tests invoke CLI and then immediately read output files:

```python
result = runner.invoke(
    app,
    ["run", "-s", str(settings_file), "--execute"],
    env={"ELSPETH_SIGNING_KEY": key},
)
# Immediately reads file
records = json.loads(audit_json.read_text())
```

If the CLI uses async operations or background threads for file writing, there's a potential race condition where the file read happens before the write is flushed.

**Mitigation:** The CLI should block until all writes complete. Verify this is the case.

### 3. COVERAGE: Missing Export Error Cases

**Severity:** Medium

Missing tests for:
- Export when run is incomplete/in-progress
- Export when database has corrupt/missing records
- Export with very large payloads (memory pressure)
- Export with payload store references (are payloads included?)
- Re-export after run modification (if possible)

### 4. STRUCTURAL: Fixture Returns Path but Test Uses `tmp_path`

**Severity:** Low
**Location:** Lines 86-97, 110-128

The `export_settings_yaml` fixture returns `settings_file` path but tests also receive `tmp_path` to locate the output:

```python
def test_run_with_export_creates_audit_file(self, export_settings_yaml: Path, tmp_path: Path) -> None:
    # ...
    audit_json = tmp_path / "audit_export.json"  # Relies on fixture using same tmp_path
```

This works because pytest's `tmp_path` is the same for fixtures and tests in the same scope, but it's implicit coupling. The fixture could return a dataclass with both paths for clarity.

### 5. GOOD: Comprehensive Record Type Verification

Test `test_export_contains_all_record_types` properly verifies all expected record types are present:
```python
assert "run" in record_types
assert "node" in record_types
assert "row" in record_types
assert "token" in record_types
```

### 6. STRUCTURAL: Duplicate Configuration Blocks

**Severity:** Low
**Location:** Multiple fixtures

The YAML configuration is duplicated across `export_settings_yaml`, `export_disabled_settings`, and inline in `TestSignedExportDeterminism` tests. This violates DRY and makes maintenance harder.

**Recommendation:** Create a helper function to generate base config with optional overrides:
```python
def make_export_config(tmp_path, export_enabled=True, sign=False, **overrides):
    ...
```

### 7. GOOD: Sign Key Dependency Test

`test_different_signing_keys_produce_different_hashes` correctly verifies signatures depend on the key:
```python
assert final_hashes[0] != final_hashes[1], "Different keys produced same hash - signature not key-dependent!"
```

### 8. COVERAGE: No Test for Unsigned Export Format

**Severity:** Low

Tests verify signed export has signatures, but there's no explicit test verifying unsigned export (with `sign: False`) does NOT include signature fields.

### 9. GOOD: Test Independence

Each test creates its own database and output files via `tmp_path`, ensuring isolation.

## Test Path Integrity

**Status:** PASS

Tests use production code paths:
- `CliRunner` invokes actual CLI (`elspeth.cli.app`)
- `LandscapeDB`, `LandscapeRecorder` used directly in unit-style tests
- `LandscapeExporter` used directly for determinism test
- No manual graph construction or attribute manipulation

## Recommendations

1. **High Priority:** Verify CLI blocks until file writes complete (no race condition)
2. **Medium Priority:** Add tests for export error cases (incomplete runs, corrupt data)
3. **Medium Priority:** Refactor duplicate config into shared helper
4. **Low Priority:** Add test verifying unsigned export has no signature fields
5. **Enhancement:** Return structured data from fixture instead of relying on implicit `tmp_path` coupling
