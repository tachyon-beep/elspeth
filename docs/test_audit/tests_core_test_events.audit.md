# Test Audit: tests/core/test_events.py

**Lines:** 236
**Test count:** 15
**Audit status:** ISSUES_FOUND

## Summary

This file tests the EventBus infrastructure used for CLI observability. The tests cover subscribe/emit functionality, multiple subscribers, handler ordering, event type isolation, exception propagation, and the NullEventBus implementation. Overall coverage is good but there are structural issues with test class naming.

## Findings

### 🟡 Warning

1. **Lines 172-193: Incorrect test class naming** - Class `SampleEventBusProtocol` and `SampleEventBusEdgeCases` (lines 196-236) are named with `Sample` prefix but should use `Test` prefix to be discovered by pytest. As written, these test methods will NOT be executed by pytest's default collection.

   - `SampleEventBusProtocol` should be `TestEventBusProtocol`
   - `SampleEventBusEdgeCases` should be `TestEventBusEdgeCases`

   This means 4 tests are silently not running:
   - `test_eventbus_satisfies_protocol`
   - `test_nulleventbus_satisfies_protocol`
   - `test_subscribe_same_handler_multiple_times`
   - `test_handler_can_emit_events`

### 🔵 Info

1. **Lines 94-95: Lambda usage in tests** - Using lambdas for simple event handlers is concise and appropriate here.

2. **Lines 111-122: Exception propagation test** - Correctly verifies that handler exceptions propagate (crash on bug behavior per CLAUDE.md).

3. **Lines 124-143: Fail-fast behavior test** - Good test for verifying that exception in handler1 stops handler2 from being called.

## Verdict

**REWRITE** - The test file has correct test logic but the class naming issue means 4 tests are not being executed. This is a silent test gap. Rename `SampleEventBusProtocol` to `TestEventBusProtocol` and `SampleEventBusEdgeCases` to `TestEventBusEdgeCases`.
