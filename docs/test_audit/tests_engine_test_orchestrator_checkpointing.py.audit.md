# Test Audit: tests/engine/test_orchestrator_checkpointing.py

**Lines:** 718
**Test count:** 8 test methods
**Audit status:** ISSUES_FOUND

## Summary

This test file provides comprehensive coverage of the orchestrator's checkpointing functionality, including checkpoint creation frequency, interval-based checkpointing, checkpoint preservation on failure, and graceful handling when checkpointing is disabled. The tests properly use production graph construction via `build_production_graph()`. However, there is significant code duplication with nearly identical plugin class definitions repeated across tests.

## Findings

### Warning

1. **Extreme code duplication** (lines 95-145, 194-243, 284-333, 384-464, 565-614, 649-698): The same `ListSource`, `IdentityTransform`/`PassthroughTransform`, and `CollectSink` classes are defined nearly identically in 6+ test methods. These should be extracted to module-level or fixture scope to reduce ~400 lines of duplication.

2. **Module-scoped database with test isolation concerns** (lines 30-39): While the comment states "Each test generates a unique run_id," sharing an in-memory database across tests could lead to subtle data pollution. Test isolation would be cleaner with function-scoped databases.

3. **Manual graph construction in `test_checkpoint_preserved_on_failure`** (lines 474-503): This test manually constructs an `ExecutionGraph` with private field mutations (`_sink_id_map`, `_transform_id_map`, `_config_gate_id_map`, `_route_resolution_map`, `_default_sink`) instead of using the production `from_plugin_instances()` factory. This violates CLAUDE.md's "Test Path Integrity" guidance and could mask production bugs.

4. **Weak assertion in failure preservation test** (lines 535-539): The assertion logic `if len(good_sink.results) > 0` makes the test outcome dependent on non-deterministic sink ordering. The test documents this weakness but doesn't resolve it.

### Info

5. **Good use of method tracking** (lines 86-93, 184-192, 556-563): Tests properly track checkpoint manager method calls to verify behavior rather than just checking state, which is a strong testing pattern.

6. **Production graph helper usage** (lines 161, 261, 350, etc.): Most tests correctly use `build_production_graph(config)` to ensure production code paths are exercised.

## Verdict

**REWRITE** - The file tests important functionality correctly, but the extreme code duplication (~400 lines of repeated plugin class definitions) significantly hurts maintainability. Extract shared test plugins to module level or fixtures. Additionally, the manual graph construction in `test_checkpoint_preserved_on_failure` should be refactored to use production factories to maintain test path integrity.
