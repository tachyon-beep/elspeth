# Test Audit: tests/core/test_logging.py

**Lines:** 146
**Test count:** 9
**Audit status:** PASS

## Summary

This file tests the structured logging configuration including JSON output, console output, context binding, third-party logger silencing, and stdlib logger integration. The tests verify correct behavior for both structlog and stdlib loggers, which is important for the P2-2026-01-31 bug fix ensuring consistent JSON output from all loggers.

## Findings

### 🔵 Info

1. **Lines 13-26: Existence/interface tests** - Tests `test_get_logger_exists`, `test_get_logger_returns_logger`, and `test_configure_logging_exists` verify basic API contracts. While simple, they provide useful regression protection.

2. **Lines 24-26: hasattr usage** - Using `hasattr()` here is appropriate because we are testing the public interface contract of the logger object, not defending against our own code bugs.

3. **Lines 75-104: Third-party logger silencing** - Good test coverage for ensuring noisy loggers (Azure SDK, urllib3, OpenTelemetry) are silenced to WARNING level even when ELSPETH is in DEBUG mode.

4. **Lines 106-146: stdlib logger integration** - Tests for P2-2026-01-31 verify that stdlib loggers produce consistent JSON output when json_output=True. This is critical for mixed-logging environments.

5. **Lines 81: Duplicate import** - `import logging` appears at line 81 inside the test method, but logging is already imported at line 5. This is redundant but harmless.

## Verdict

**KEEP** - The tests are comprehensive and cover both structlog and stdlib logger integration. The tests reference the relevant bug ticket (P2-2026-01-31) and verify critical output format consistency.
