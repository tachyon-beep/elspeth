# Audit: tests/telemetry/exporters/test_otlp.py

## Summary
**Lines:** 648
**Test Classes:** 7 (TraceIdDerivation, SpanIdDerivation, Configuration, Buffering, SpanConversion, Lifecycle, SDKCompatibility)
**Quality:** EXCELLENT - Comprehensive with critical SDK compatibility tests

## Findings

### Strengths

1. **ID Derivation Property Tests** (Lines 35-133)
   - Tests trace_id determinism (same run_id -> same trace_id)
   - Tests span_id uniqueness (different events -> different span_ids)
   - Tests ID size bounds (128-bit trace_id, 64-bit span_id)
   - Tests token_id incorporation in span_id

2. **SDK Encoder Compatibility** (Lines 580-648)
   - **CRITICAL TEST** at Line 586: Verifies `_SyntheticReadableSpan` works with actual OTLP encoder
   - Tests `encode_spans()` with real SDK encoder
   - Catches SDK compatibility issues mocked tests would miss
   - Verifies `dropped_attributes`, `dropped_events`, `dropped_links` properties exist

3. **Configuration Validation** (Lines 136-216)
   - Missing endpoint raises error
   - Empty endpoint accepted (SDK validates later)
   - batch_size validation
   - Headers passed correctly

4. **Buffering Semantics** (Lines 219-299)
   - Events buffered until batch_size
   - flush() exports partial batch
   - flush() is no-op when empty
   - export without configure is safe

5. **Span Conversion** (Lines 301-470)
   - All field types covered (datetime, enum, tuple, None, dict)
   - Dict serialized as JSON string (OTLP limitation documented)
   - trace_id derived from run_id

### Minor Issues

1. **Patch Path** (Line 32)
   - `OTLP_EXPORTER_PATCH = "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"`
   - Long path - if OTLP SDK restructures, this breaks

2. **Test Isolation** (Lines 222-234)
   - `_create_configured_exporter` exits context manager, leaving mock in place
   - Works because mock is stored in instance, but pattern is unusual

### Excellent Documentation

- Line 586-589: Explains why this test is critical
- Line 446: Documents OTLP limitation for dict fields
- Comments throughout explain OpenTelemetry specifics

## Verdict
**PASS** - Excellent test suite with the SDK compatibility tests being particularly valuable. These tests would catch SDK upgrade regressions.
