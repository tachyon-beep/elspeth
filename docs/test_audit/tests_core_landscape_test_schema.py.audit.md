# Test Audit: tests/core/landscape/test_schema.py

**Lines:** 232 (originally stated, actual is 231)
**Test count:** 17 test functions
**Audit status:** PASS

## Summary

This test file validates the Landscape SQLAlchemy schema definition, including table existence, column presence, model field alignment, and enum value correctness. The tests serve as a schema contract to catch regressions in the database structure.

## Findings

### 🔵 Info

1. **Schema existence tests (lines 13-31, 127-139)**: Tests verify that expected tables exist after `metadata.create_all()`. This catches schema definition errors that would prevent database creation.

2. **Column presence tests (lines 37-41, 81-98, 177-181, 216-221)**: Multiple tests verify specific columns exist in tables (determinism, idempotency_key, trigger_type, topology validation columns). These serve as regression guards.

3. **Non-nullable constraint tests (lines 100-119)**: Tests explicitly verify that `upstream_topology_hash` and `checkpoint_node_config_hash` are non-nullable, with comments explaining why (checkpoint validation integrity). This is good defensive testing.

4. **Model-schema alignment tests (lines 43-59, 141-171, 184-191, 223-230)**: Tests verify that model dataclasses have fields matching the schema columns. This catches drift between schema and models.

5. **Enum value completeness test (lines 61-75)**: Test verifies all 6 Determinism enum values exist with exact expected string values. This catches enum definition changes.

6. **Test organization by feature**: Classes group related tests (TestNodesDeterminismColumn, TestPhase5CheckpointSchema, TestArtifactsIdempotencyKey, TestBatchStatusType, TestBatchesTriggerType).

7. **Uses tmp_path fixture appropriately (lines 13, 127)**: File-based tests use pytest's tmp_path fixture for test isolation.

### 🟡 Warning

1. **Redundant datetime import (line 44)**: `datetime` is imported at module level (line 4) and again inside `test_node_model_has_determinism_field`. This is harmless but inconsistent.

## Verdict

**KEEP** - Valuable schema regression tests that protect database structure integrity. The tests serve as living documentation of schema requirements and catch accidental column/table removals.
