# Audit: tests/telemetry/test_property_based.py

## Summary
**Lines:** 866
**Test Classes:** 6 (2 StateMachines, BoundedBuffer, Granularity, Ordering, ManagerInvariants)
**Quality:** EXCELLENT - Sophisticated property-based testing with Hypothesis

## Findings

### Strengths

1. **Stateful Testing with Hypothesis** (Lines 324-452)
   - `TelemetryManagerStateMachine` tests failure handling state transitions
   - Uses `@rule` and `@invariant` decorators correctly
   - Tracks parallel model state for verification
   - Tests: metrics consistency, disabled state stickiness, consecutive failure bounds

2. **All-Exporters-Fail State Machine** (Lines 455-512)
   - Separate state machine for total failure scenario
   - Verifies dropped count frozen after disable
   - Verifies disable happens at exactly threshold (10)

3. **BoundedBuffer Property Tests** (Lines 520-590)
   - `len(buffer) <= max_size` invariant
   - `dropped_count == max(0, total_added - max_size)` formula
   - FIFO ordering preserved
   - Conservation: `len + dropped == added`

4. **Granularity Filtering Matrix** (Lines 597-710)
   - Complete matrix of event_type x granularity expected behavior
   - Tests unknown event types pass through (forward compatibility)
   - `EXPECTED_MATRIX` class variable documents spec

5. **Event Ordering Tests** (Lines 718-794)
   - Events exported in emit order
   - All exporters receive same order
   - Buffer preserves order across batches

6. **Well-Designed Strategies** (Lines 236-316)
   - `run_id_strategy` - valid identifiers with reasonable length
   - `timestamp_strategy` - bounded datetimes with UTC timezone
   - Composite strategies for each event category

### Minor Issues

1. **DTZ001 Exception** (Lines 253-256)
   - `# noqa: DTZ001` for naive datetime bounds
   - Documented: "Hypothesis requires naive datetimes for min/max bounds"
   - Acceptable workaround

2. **State Machine Registration** (Lines 452, 512)
   - `TestTelemetryManagerStateMachine = TelemetryManagerStateMachine.TestCase`
   - Standard Hypothesis pattern but can be confusing

### Settings Tuning

- `@settings(max_examples=100)` or `max_examples=50` throughout
- Balances thoroughness with test runtime
- Could increase for CI runs with `@settings(max_examples=500, deadline=None)`

### Excellent Design Patterns

1. **ToggleableExporter** (Lines 115-125) - Exporter that can switch between working/failing
2. **MockConfig dataclass** (Lines 56-72) - Minimal config for testing
3. **Event factories** (Lines 133-227) - Consistent event creation

## Verdict
**PASS** - Excellent property-based testing suite. The state machines for failure handling are particularly valuable for finding edge cases.
