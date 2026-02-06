# Test Audit: tests/engine/test_orchestrator_audit.py

**Lines:** 1424
**Test count:** 12
**Audit status:** ISSUES_FOUND

## Summary

Comprehensive integration test suite for orchestrator audit trail functionality. Tests cover core audit recording, landscape export (with/without signing), config recording, and node metadata inheritance. The tests use real LandscapeDB instances and properly exercise production code paths. However, there is significant code duplication that could be reduced, and some tests manually construct ExecutionGraph instead of using production factories.

## Findings

### 🟡 Warning

1. **Manual ExecutionGraph construction (lines 920-929, 1035-1044)**: Tests `test_node_metadata_records_plugin_version` and `test_node_metadata_records_determinism` manually construct `ExecutionGraph` with `add_node()` and `add_edge()`, then directly assign private attributes (`_transform_id_map`, `_sink_id_map`, `_default_sink`). This violates CLAUDE.md "Test Path Integrity" - should use `ExecutionGraph.from_plugin_instances()`.

2. **Excessive code duplication (throughout)**: `ListSource`, `CollectSink`, and `ValueSchema` classes are redefined in nearly every test method (approximately 10+ times). This makes tests harder to maintain and increases file size significantly. These should be module-level or class-level fixtures.

3. **Test helper class definitions inside test methods (lines 43-91, 183-230, etc.)**: Defining test plugins inside test methods is verbose. While it provides isolation, it creates 1400+ lines of largely repetitive code.

### 🔵 Info

1. **Good production path usage in some tests (lines 275-285, 1382-1392)**: Tests like `test_orchestrator_exports_landscape_when_configured` and `test_coalesce_node_uses_engine_version` correctly use `instantiate_plugins_from_config` and `ExecutionGraph.from_plugin_instances`.

2. **Comprehensive export testing (lines 166-661)**: Four tests covering export enabled/disabled, signing, and missing signing key - good coverage of the landscape export feature.

3. **Bug fix verification tests (lines 834-1424)**: Tests explicitly document which bugs they verify (e.g., `BUG FIX: P2-2026-01-21-orchestrator-aggregation-metadata-hardcoded`). This is excellent for regression prevention.

4. **Uses `build_production_graph` helper (lines 104, 747, 821)**: Some tests use a helper that presumably follows production paths - good pattern.

5. **Real LandscapeDB usage (throughout)**: Tests use `LandscapeDB.in_memory()` rather than mocking, which validates actual database interactions.

### 🔴 Critical

1. **Inconsistent graph construction patterns**: The file mixes production-path graph construction (via `from_plugin_instances`) with manual construction (via `add_node`/`add_edge`). This inconsistency means some bugs might be caught by some tests but not others, and creates maintenance burden to understand which tests use which pattern.

## Verdict

**REWRITE** - The tests are valuable and should be kept, but the file needs refactoring:
1. Extract common test plugin classes (`ListSource`, `CollectSink`, `ValueSchema`) to module level or a shared test utilities module
2. Fix tests that manually construct `ExecutionGraph` to use `from_plugin_instances`
3. Consider splitting into multiple files by feature (audit_trail, export, metadata) given the 1400+ line size

The core test logic is sound; the issues are structural and maintainability-related.
