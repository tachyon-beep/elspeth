# Test Audit: tests/engine/test_checkpoint_durability.py

**Lines:** 1203
**Test count:** 8 test functions across 2 test classes
**Audit status:** ISSUES_FOUND

## Summary

This is a well-structured test file that verifies critical checkpoint durability invariants - ensuring checkpoints are created AFTER sink writes complete, not during processing. The tests are comprehensive and use realistic end-to-end scenarios with proper audit trail verification. However, there is significant code duplication in test helper classes and some tests could benefit from parametrization.

## Findings

### 🟡 Warning

1. **Excessive Code Duplication (Lines 175-236, 326-382, 634-686, etc.)** - The same `ListSource`, `PassthroughTransform`, and various sink classes are redefined nearly identically in multiple tests. These should be factored into shared fixtures or module-level test utilities. Each test class recreates `RowSchema`, `ListSource`, and transform classes that differ only in minor ways.

2. **Helper Function `_build_production_graph` Uses Private Fields (Lines 129-134)** - The function directly assigns to private fields (`_sink_id_map`, `_transform_id_map`, etc.) which violates encapsulation. The comment acknowledges this but the test still bypasses production code paths for graph construction.

3. **Test `test_crash_before_sink_write_recovers_correctly` is 285 lines (Lines 297-586)** - This single test is extremely long and could be split into setup/verification phases or use shared fixtures. While it tests an important recovery scenario thoroughly, its length makes it harder to maintain.

4. **Inconsistent Schema Usage** - Tests create `RowSchema` as a `PluginSchema` subclass but then use `_make_pipeline_row()` with `OBSERVED` mode which ignores the schema. The schema definitions appear decorative rather than functional.

### 🔵 Info

1. **Excellent Documentation** - The file has thorough docstrings explaining the checkpoint timing model and why each invariant matters. The module docstring clearly explains the test strategy.

2. **Good P1/P2/P3 Fix Annotations** - Comments like "P1 Fix: Verify audit trail records" indicate these tests were added to address specific bug fixes, showing good traceability.

3. **Real Integration Testing** - Tests use actual `Orchestrator`, `LandscapeDB`, and `CheckpointManager` instances rather than mocks, providing strong confidence in the checkpoint system.

4. **Payload Store Fixture Shadowing (Line 321)** - The `payload_store` parameter is shadowed by a local variable assignment. This works but could cause confusion:
   ```python
   def test_crash_before_sink_write_recovers_correctly(self, tmp_path: Path, payload_store) -> None:
       ...
       payload_store = FilesystemPayloadStore(tmp_path / "payloads")  # shadows parameter
   ```

5. **Good Timing Verification** - `TestCheckpointTimingInvariants` class properly verifies checkpoint counts before/after write calls using sink hooks, which is the correct approach for timing tests.

## Verdict

**KEEP** - This test file provides critical coverage for checkpoint durability guarantees, which are essential for ELSPETH's crash recovery semantics. The tests are thorough and test real scenarios. The code duplication should be addressed in a future cleanup pass, but the tests themselves are valuable and correct. Consider extracting shared test utilities to reduce boilerplate while preserving the comprehensive coverage.
