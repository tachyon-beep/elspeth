# Test Audit: tests/engine/test_orchestrator_core.py

**Lines:** 694
**Test count:** 8 test methods across 4 test classes
**Audit status:** ISSUES_FOUND

## Summary

This test file covers core orchestrator functionality including simple pipeline execution, gate routing, multiple transforms in sequence, empty pipeline cases, and graph parameter handling. The tests correctly use production graph construction helpers. However, there is significant code duplication with plugin classes, and some tests use mocking patterns that may be overly complex.

## Findings

### Warning

1. **Repeated plugin class definitions** (lines 44-103, 130-167, 208-267, 300-337, 365-408, 658-682): `ListSource`, `CollectSink`, and various transform classes are defined repeatedly within each test method. This adds ~300 lines of duplication that could be eliminated with module-level definitions.

2. **Complex mocking in graph tests** (lines 432-521, 523-625): The tests `test_orchestrator_uses_graph_node_ids` and `test_orchestrator_assigns_unique_node_ids_to_multiple_sinks` use extensive `MagicMock` and `PropertyMock` to track node_id setter calls. While the approach is valid, the tests are testing implementation details (that `node_id` is SET) rather than behavioral outcomes. A simpler approach would verify the orchestrator's recorded nodes have the expected IDs from the graph.

3. **Missing `super().__init__()` call** (line 88): `CollectSink.__init__` doesn't call `super().__init__()`, which could cause issues if the base class initializer does anything important. (Also repeated at lines 153, 253, 323, 395, etc.)

### Info

4. **Good production graph usage** (lines 115, 188, 281, 349, 422): Tests correctly use `build_production_graph(config)` to ensure production code paths are exercised.

5. **Proper gate routing test** (lines 122-193): `test_run_with_gate_routing` correctly verifies that the gate routes rows to different sinks based on the condition.

6. **Edge case coverage** (lines 289-426): Tests for empty pipelines (no transforms, empty source) ensure the orchestrator handles degenerate cases correctly.

7. **Graph parameter enforcement** (lines 650-694): `test_orchestrator_run_requires_graph` correctly verifies that passing `graph=None` raises a `ValueError`.

8. **Signature inspection test** (lines 627-648): `test_orchestrator_run_accepts_graph` uses `inspect.signature` to verify the API contract, which is a lightweight way to test interface compliance without full execution.

## Verdict

**REWRITE** - The tests verify important functionality but suffer from excessive code duplication (~300 lines of repeated plugin definitions). Extract shared test plugins to module level. Consider simplifying the mock-heavy graph tests to verify behavioral outcomes (e.g., recorded node IDs in the database) rather than setter calls.
