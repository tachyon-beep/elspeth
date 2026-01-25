# Test Quality Review: test_audit.py

## Summary

This test suite validates contract dataclasses but provides **zero assurance of audit integrity**. Tests verify dataclass field assignment works (basic Python functionality) without testing auditability requirements, invariants, or edge cases. No validation testing, no constraint enforcement, no hash verification, no enum boundary testing, no immutability verification beyond one token test. This is a smoke test masquerading as a contract validation suite.

## Poorly Constructed Tests

### Test: test_create_run_with_required_fields (line 37)
**Issue**: Assertion-free test for critical audit requirements
**Evidence**: Creates `Run` but never validates that `config_hash`, `settings_json`, or `canonical_version` are actually required. Missing validation that these fields cannot be empty strings or None.
**Fix**: Add negative tests verifying Pydantic/dataclass validation rejects invalid values. Test that `config_hash=""` raises ValidationError, that `canonical_version=None` fails construction.
**Priority**: P1 - Audit trail integrity depends on these fields being present and valid

### Test: test_run_status_must_be_enum (line 55)
**Issue**: Tests obvious Python behavior, not contract invariants
**Evidence**: Lines 66-69 verify that enum fields work like enums (`.value` accessor exists). This is testing Python's enum implementation, not ELSPETH's contracts.
**Fix**: Test enum boundary violations - verify `status="invalid_string"` raises TypeError, not that `status.value == "completed"` works.
**Priority**: P2 - Low-value test, replace with boundary testing

### Test: test_run_with_export_status (line 71)
**Issue**: Duplicate of previous test, no new assertions
**Evidence**: Creates Run with ExportStatus enum, asserts `run.export_status.value == "pending"` - same pattern as test_run_status_must_be_enum.
**Fix**: Delete test or repurpose to verify optional field behavior (can be None, transitions from None to PENDING are valid).
**Priority**: P2 - Test redundancy

### Test: test_frozen_dataclass_immutable (line 350)
**Issue**: Only ONE immutability test for entire suite
**Evidence**: Only `NodeStateOpen` tested for immutability. No tests for Run, Node, Edge, Row, Token, Call, Artifact, Batch, etc.
**Fix**: Use parametrized test covering ALL frozen dataclasses or property test with Hypothesis to verify frozen constraint universally.
**Priority**: P1 - Audit integrity requires immutability across all contracts

### Test: test_node_type_is_enum / test_determinism_is_enum (lines 109, 127)
**Issue**: Repetitive enum accessor tests with zero boundary validation
**Evidence**: Lines 123-125 test `node.node_type.value == "gate"` - redundant with line 123 `node.node_type == NodeType.GATE`. No test for invalid enum values.
**Fix**: Remove `.value` accessor tests, add boundary tests: `NodeType("invalid")` raises ValueError, that typos in config files fail fast.
**Priority**: P2 - Replace low-value tests with boundary tests

### Test: test_union_type_annotation (line 335)
**Issue**: Tests type checker behavior, not runtime contract
**Evidence**: Lines 338-348 assign `NodeStateOpen` to `NodeState` union type and assert `state is not None`. This validates type annotations work, not that discriminated union logic is correct.
**Fix**: Test discriminator field enforcement - verify cannot create `NodeStateCompleted` without `output_hash`, cannot create base `NodeState` directly, status field discriminates correctly.
**Priority**: P1 - Discriminated unions are critical for audit trail type safety

### Test: test_completed_state_requires_output (line 298)
**Issue**: Tests successful construction, not requirement enforcement
**Evidence**: Creates `NodeStateCompleted` with all required fields but never tests that omitting `output_hash` or `completed_at` raises error.
**Fix**: Add negative test: `NodeStateCompleted(..., output_hash=None)` must fail construction.
**Priority**: P0 - Critical audit requirement: completed states MUST have output hashes

### Test: test_failed_state_has_error_fields (line 316)
**Issue**: Only tests successful case, not error_json structure
**Evidence**: Sets `error_json='{"error": "something went wrong"}'` but never validates it's valid JSON, that malformed JSON is rejected, or that error_json can be None for transient failures.
**Fix**: Test error_json validation - malformed JSON rejected, None accepted, verify error structure is preserved byte-for-byte.
**Priority**: P1 - Error data is part of audit trail

### Test: test_artifact_type_is_string_not_enum (line 465)
**Issue**: Documents anti-pattern without testing safety constraints
**Evidence**: Lines 479-481 confirm `artifact_type` accepts "any string" but no test for empty string, whitespace-only, or excessively long values that could break storage.
**Fix**: Test edge cases - empty string, 10KB string, Unicode, control characters. If unconstrained strings are unsafe, add validation and test it.
**Priority**: P1 - Unbounded user input to audit trail

### Test: test_row_lineage_with_purged_payload (line 737)
**Issue**: Critical auditability test with insufficient assertions
**Evidence**: Tests payload degradation but doesn't verify that `source_data_hash` can still validate integrity when payload is restored from backup or that hash verification still works.
**Fix**: Test hash verification explicitly - verify hash matches source_data when available, verify hash is immutable even when payload purged, test hash collision detection.
**Priority**: P0 - Hash integrity is core auditability guarantee

### Test: test_row_lineage_hash_always_present (line 757)
**Issue**: Tests presence but not validity or immutability
**Evidence**: Lines 773 assert `lineage.source_data_hash == "required_hash_value"` but never tests that hash cannot be empty, cannot be modified, cannot be None, must be valid hex/base64 format.
**Fix**: Test hash format validation - reject empty string, reject "not-a-hash", reject wrong length, verify hash format matches canonical hash output.
**Priority**: P0 - Invalid hashes destroy audit integrity

## Misclassified Tests

### Suite Classification: Should be split into unit + property tests
**Issue**: All tests are unit tests but missing property-based tests for invariants
**Evidence**: No use of Hypothesis despite CLAUDE.md listing it as acceleration stack technology for "property testing". Contracts have universal invariants (immutability, enum boundaries, hash formats) that should be property-tested.
**Fix**: Create `test_audit_properties.py` using Hypothesis to test:
- All frozen dataclasses are immutable (generate instances, verify mutation fails)
- All hash fields have valid format (generate random strings, verify validation)
- All enum fields reject invalid values (generate arbitrary strings)
- All required fields cannot be None (generate instances with st.none())
**Priority**: P0 - Missing entire class of tests for critical properties

### Tests: All enum tests (lines 55, 71, 109, 127, 165, 391, 407, 504, 558)
**Issue**: Should be single parametrized test, not 9 separate methods
**Evidence**: Nine nearly-identical tests verifying enum fields work like enums.
**Fix**: Replace with pytest parametrized test covering all enum fields:
```python
@pytest.mark.parametrize("model_cls,field,enum_cls,valid_value", [
    (Run, "status", RunStatus, RunStatus.COMPLETED),
    (Node, "node_type", NodeType, NodeType.SOURCE),
    # ... all enum fields
])
def test_enum_fields_accept_valid_values(model_cls, field, enum_cls, valid_value):
    # Test construction with valid enum
    # Test rejection of invalid string
```
**Priority**: P1 - Test suite maintainability

## Infrastructure Gaps

### Gap: No shared fixtures for common test data
**Issue**: Every test constructs `datetime.now(UTC)` independently
**Evidence**: Line 39, 59, 92, 120, 138, 151, 174, 187, etc. - 40+ instances of `datetime.now(UTC)`.
**Fix**: Create pytest fixture:
```python
@pytest.fixture
def fixed_timestamp() -> datetime:
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
```
Use fixed timestamp for deterministic tests, avoid time-based flakiness.
**Priority**: P2 - Test determinism and readability

### Gap: No fixtures for valid ID formats
**Issue**: Tests use arbitrary strings for IDs without validating format
**Evidence**: `run_id="run-123"`, `node_id="node-1"`, `token_id="tok-123"` - inconsistent formats suggest no ID validation.
**Fix**: Create fixtures for valid IDs, test that malformed IDs (empty, whitespace, wrong prefix) are rejected if validation exists, or add validation if missing.
**Priority**: P1 - ID format consistency for audit queries

### Gap: No hash validation infrastructure
**Issue**: Tests use placeholder hashes without format validation
**Evidence**: `config_hash="abc123"` (line 43), `source_data_hash="abc123"` (line 193), `upstream_topology_hash="a" * 64` (line 661) - inconsistent formats.
**Fix**: Create hash validation fixtures:
```python
@pytest.fixture
def valid_sha256_hash() -> str:
    return "a" * 64  # Valid SHA-256 hex string

@pytest.fixture
def invalid_hashes() -> list[str]:
    return ["", "short", "not-hex", "z" * 64]
```
Test that contracts validate hash format if applicable.
**Priority**: P0 - Hash format critical for integrity verification

### Gap: No negative test infrastructure
**Issue**: Zero tests verify that invalid construction fails
**Evidence**: No `pytest.raises` blocks except frozen dataclass test (line 365). No ValidationError tests, no TypeError tests for wrong types.
**Fix**: Create parametrized negative test fixture:
```python
@pytest.mark.parametrize("invalid_field,invalid_value,expected_error", [
    ("run_id", None, ValidationError),
    ("status", "invalid", TypeError),
    ("started_at", "not-a-datetime", ValidationError),
])
def test_run_rejects_invalid_fields(invalid_field, invalid_value, expected_error):
    with pytest.raises(expected_error):
        Run(**{invalid_field: invalid_value, **VALID_RUN_DEFAULTS})
```
**Priority**: P0 - Validation testing completely missing

### Gap: No relationship/referential integrity tests
**Issue**: Models have foreign key relationships but no constraint tests
**Evidence**: `Token.row_id` references `Row.row_id`, `NodeState.node_id` references `Node.node_id`, but no tests verify constraints.
**Fix**: If referential integrity is enforced at database level (not dataclass), document that these are schema tests only. If enforced in code, test it. Create integration tests for database constraints.
**Priority**: P1 - Audit trail consistency depends on referential integrity

### Gap: No serialization round-trip tests
**Issue**: Dataclasses will be serialized to/from database but no testing
**Evidence**: No tests for JSON serialization, no tests for database row conversion, no tests that datetime/enum serialization is reversible.
**Fix**: Test serialization round-trips:
```python
def test_run_json_serialization_roundtrip():
    original = Run(...)
    json_str = to_json(original)  # Whatever serialization is used
    deserialized = from_json(json_str, Run)
    assert deserialized == original
```
**Priority**: P1 - Serialization bugs will corrupt audit trail

### Gap: No tests for discriminated union exhaustiveness
**Issue**: NodeState union has 3+ variants but no test verifying all are handled
**Evidence**: Tests create individual variants (OPEN, COMPLETED, FAILED) but no test that pattern matching or isinstance checks cover all cases.
**Fix**: Test that discriminator field `status` has exactly expected variants, that adding new variant without updating handler code fails CI.
**Priority**: P1 - Missing variant handlers will corrupt audit trail

## Positive Observations

- **Frozen dataclass test exists** (line 350) - Only test checking immutability, proves pattern works
- **Enum usage is correct** - Tests consistently use enum values, not strings (even if testing is shallow)
- **Naming is clear** - Test names describe what's being tested (even if assertions are weak)
- **Discriminated union structure tested** - NodeStateOpen/Completed/Failed variants are instantiated correctly

## Summary Statistics

- **Total tests**: 54
- **Tests with no negative cases**: 53 (98%)
- **Tests verifying obvious Python behavior**: ~15 (28%)
- **Tests covering audit requirements**: ~5 (9%)
- **Duplicate/redundant tests**: ~10 (19%)
- **Property-based tests**: 0
- **Serialization tests**: 0
- **Relationship integrity tests**: 0

## Recommended Action Plan

1. **Immediate (P0)**: Add negative validation tests for required fields, hash formats, enum boundaries
2. **Immediate (P0)**: Add property tests using Hypothesis for immutability, format validation, enum constraints
3. **Before RC-2 (P1)**: Add serialization round-trip tests for all dataclasses
4. **Before RC-2 (P1)**: Consolidate enum tests into parametrized suite
5. **Before RC-2 (P1)**: Create shared fixtures for timestamps, IDs, hashes
6. **Nice-to-have (P2)**: Remove redundant tests, add integration tests for referential integrity

**Bottom line**: This suite tests Python's dataclass implementation, not ELSPETH's audit contracts. Rewrite with focus on invariants, boundaries, and failure modes.
