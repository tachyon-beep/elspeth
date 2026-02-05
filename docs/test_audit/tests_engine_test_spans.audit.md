# Test Audit: tests/engine/test_spans.py

**Lines:** 839
**Test count:** 34
**Audit status:** PASS

## Summary

This is a thorough test file for the OpenTelemetry `SpanFactory`. It covers both no-op mode (when telemetry is disabled) and real tracer mode. Tests validate span creation, attribute propagation, nested spans, and importantly the token_id/node_id attributes needed for audit correlation. The tests properly handle the optional OpenTelemetry dependency using `pytest.importorskip()`.

## Findings

### 🔵 Info

1. **Good use of pytest.importorskip()** (throughout): Tests that require OpenTelemetry gracefully skip when the dependency is unavailable, making the test suite resilient.

2. **Local TracerProvider usage** (line 42-45 and throughout): Tests explicitly avoid setting global tracer state with `set_tracer_provider()`, preventing test pollution. This is documented with a helpful comment.

3. **InMemorySpanExporter pattern** (lines 255-278 and throughout): Tests use `InMemorySpanExporter` to capture and validate span attributes, which is the correct pattern for testing OpenTelemetry instrumentation.

4. **Dynamic import workaround** (lines 263, 291, etc.): Uses `__import__("opentelemetry.sdk.trace.export", fromlist=["SimpleSpanProcessor"])` pattern. This works but is slightly unusual - could be simplified with a regular import at the test level after `importorskip()`.

5. **Comprehensive token.id coverage** (lines 242-417): Tests validate that child spans (transform, gate, sink) carry correct token_id attributes, including edge cases like:
   - Fork scenarios where parent and child have different token_ids
   - Batch transforms with token_ids (plural)
   - Explicit None handling
   - Empty sequences

6. **node_id disambiguation tests** (lines 603-839): Tests for P2-2026-01-21-span-ambiguous-plugin-instances bug fix, ensuring multiple instances of the same plugin type are distinguishable by node_id.

7. **input_hash for aggregation spans** (lines 727-766): Tests P3-2026-02-01 fix ensuring aggregation spans include input_hash for trace-to-audit correlation.

8. **Some repetitive setup code** (span exporter setup repeated ~15 times): The pattern of creating `InMemorySpanExporter`, `TracerProvider`, `SimpleSpanProcessor`, and `SpanFactory` is repeated in many tests. A pytest fixture could reduce this, but the current approach keeps each test self-contained and explicit.

## Verdict

**KEEP** - This is a well-designed test file with comprehensive coverage of the span factory's behavior in both enabled and disabled states. The tests are thorough and document important bug fixes.
