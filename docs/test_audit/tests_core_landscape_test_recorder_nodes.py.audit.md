# Test Audit: tests/core/landscape/test_recorder_nodes.py

**Lines:** 387
**Test count:** 12
**Audit status:** PASS

## Summary

This test file covers node and edge registration in LandscapeRecorder, including schema configuration recording. Tests verify enum handling, type validation (rejecting invalid strings), edge creation with routing modes, and comprehensive schema recording for all three modes (observed/dynamic, fixed, flexible). The tests use real database operations and verify data persistence.

## Findings

### Info

1. **Good type safety testing (line 67-81):** The `test_register_node_invalid_type_raises` test explicitly verifies that passing a string instead of `NodeType` enum raises a `TypeError` with a helpful message. This is important for catching typos.

2. **Comprehensive schema mode coverage:** Tests cover all three schema modes (observed/dynamic, fixed, flexible) and verify that optional fields are correctly marked with `required: False`.

3. **Edge query coverage:** The `TestLandscapeRecorderEdges` class thoroughly tests `get_edges()` including empty result, single edge, and multiple edges from a gate routing scenario.

4. **Potential gap - node retrieval by invalid run_id:** There is no test for `get_node()` when querying with a mismatched run_id (covered in explain tests but not here).

## Verdict

**KEEP** - Solid test coverage of node/edge/schema recording. Tests verify both the happy path and error cases (invalid node type). The schema recording tests are particularly valuable for ensuring audit trail completeness. The tests exercise real SQLAlchemy operations without mocking. No structural changes needed.
