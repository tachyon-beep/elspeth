# tests/engine/test_executors.py

**Lines:** 1591
**Tests:** 28
**Audit:** WARN

## Summary

Well-structured unit tests for executor classes (TransformExecutor, GateExecutor, AggregationExecutor, SinkExecutor). Tests use real LandscapeDB/LandscapeRecorder with in-memory SQLite which is appropriate. However, there are type errors in constructor calls, missing coverage for transform exceptions, and the mock classes don't fully exercise the production code paths for some edge cases.

## Findings

### Critical

- **Type error in TransformExecutor constructor (lines 1440, 1507, 1578):** Tests pass `run.run_id` (a string) as the third argument, but TransformExecutor expects `max_workers: int | None`. The signature is `TransformExecutor(recorder, span_factory, max_workers=None)` but tests call `TransformExecutor(recorder, span_factory, run.run_id)`. This is a type mismatch that mypy should catch. The `run_id` is being silently assigned to `max_workers`.

### Warning

- **Missing test coverage for transform exceptions (lines 253-262):** MockTransform accepts a `raises` parameter to simulate exceptions, but NO tests actually use it. Tests only cover `TransformResult.error()` (lines 395-397), not the case where `transform.process()` throws an exception. This is documented as a distinct code path in the executor ("Exceptions are BUGS and propagate").

- **MockGate doesn't extend _TestGateBase (lines 473-505):** Unlike MockTransform and MockSink which extend the test base classes, MockGate is manually defined. This means it may not implement all protocol attributes correctly. Should use the pattern from conftest.py for consistency.

- **GateOutcome fork test is unit-only (lines 183-216):** `test_with_child_tokens_for_fork` only tests the GateOutcome dataclass construction, not the actual `GateExecutor.execute_gate()` fork behavior. However, this is mitigated by dedicated coverage in `/home/john/elspeth-rapid/tests/engine/test_gate_executor.py`.

- **Inconsistent TransformExecutor constructor calls:** Lines 311, 365, 423, 457 use 2 arguments (correct), while lines 1440, 1507, 1578 use 3 arguments with run_id (incorrect). The latter tests in TestTransformCanonicalValidation are using the wrong signature.

### Info

- **Fixture creates fresh DB per test (lines 91-97):** The `landscape_setup` fixture creates an in-memory SQLite database for each test. This is appropriate for isolation but could be slow at scale. Currently acceptable for 28 tests.

- **Helper `_make_pipeline_row` is well-designed (lines 66-83):** Creates PipelineRow with OBSERVED schema for flexibility in tests.

- **Checkpoint roundtrip test is thorough (lines 1033-1101):** `test_checkpoint_state_roundtrip` properly tests save/restore of aggregation state.

- **Proper edge_map usage in GateExecutor tests (lines 573, 650):** Tests correctly create edge_map from actual edge_id values returned by `register_edge()`, not fabricated IDs.

- **AggregationExecutor tests (lines 763-1126):** Well-structured tests for buffer operations, trigger evaluation, and checkpoint state. Uses real landscape DB with proper FK setup.

## Verdict

**WARN** - Fix the type error in TransformExecutor constructor calls in TestTransformCanonicalValidation (lines 1440, 1507, 1578) - should be `TransformExecutor(recorder, span_factory)` without the run_id argument. Add test coverage for transform exceptions using the existing `raises` parameter in MockTransform.
