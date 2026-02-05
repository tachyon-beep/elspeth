# Test Audit: tests/integration/test_retry_integration.py

**Auditor:** Claude
**Date:** 2026-02-05
**Batch:** 105-106

## Overview

This file contains integration tests for retry behavior with audit trail verification. Tests prove that retry attempts are auditable - each attempt creates a separate node_state record in the database. Also includes regression tests for the P2-2026-01-21 bug where `exponential_base` was ignored.

**Lines:** 746
**Test Classes:**
- `TestRetryAuditTrail` (3 tests)
- `TestRetryExponentialBackoff` (3 tests)
- `TestExponentialBaseRegressionP2_2026_01_21` (3 tests)

**Total Test Count:** 9

---

## Summary

| Category | Issues Found |
|----------|--------------|
| Defects | 0 |
| Test Path Integrity Violations | 0 |
| Overmocking | 1 (MINOR) |
| Missing Coverage | 1 |
| Tests That Do Nothing | 0 |
| Structural Issues | 0 |
| Inefficiency | 1 |

---

## Issues

### 1. [MINOR] SpanFactory Mock in Test Environment

**Location:** `test_env` fixture (lines 104-113)

**Problem:** The SpanFactory is mocked with a minimal spec that may not reflect production behavior:

```python
# Create a noop span factory
span_factory = Mock(spec=SpanFactory)
span_factory.transform_span.return_value.__enter__ = Mock(return_value=None)
span_factory.transform_span.return_value.__exit__ = Mock(return_value=None)
```

**Assessment:** This is acceptable for these tests because:
1. The tests focus on retry audit trail behavior, not telemetry
2. SpanFactory is properly isolated as a context manager
3. The spec ensures the mock has the right interface

**Recommendation:** No action needed, but document why the mock is acceptable.

---

### 2. [MINOR] Missing Coverage - Non-Retryable Exception Handling

**Problem:** Tests cover retryable exceptions (`ConnectionError`) and exhausted retries, but don't test what happens when a non-retryable exception is raised (e.g., `TypeError`, `ValueError`).

**Recommendation:** Add a test case that verifies:
1. Non-retryable exceptions are not retried
2. A single node_state record is created with status "failed"
3. The original exception propagates correctly

---

### 3. [MINOR] Duplicate Import Pattern

**Location:** Multiple test methods import `SchemaConfig` locally

**Problem:** The same import appears inside multiple methods:

```python
# Line 204
from elspeth.contracts.schema import SchemaConfig
# Line 304
from elspeth.contracts.schema import SchemaConfig
# Line 408
from elspeth.contracts.schema import SchemaConfig
```

**Recommendation:** Move to top-level imports for cleaner code.

---

## Strengths

### Excellent Test Design

1. **Uses Production Code Paths:** `TransformExecutor`, `RetryManager`, and `LandscapeRecorder` are real implementations
2. **Verifies Database State:** Tests query `node_states_table` to verify retry attempts are recorded correctly
3. **Clear Test Scenarios:** Each test has well-documented scenarios with numbered steps
4. **Regression Tests:** Dedicated class for P2-2026-01-21 regression with multiple verification angles

### Comprehensive Backoff Testing

The `TestRetryExponentialBackoff` class uses an innovative approach:
- Patches `wait_exponential_jitter` to capture the actual `exp_base` argument
- Verifies the complete config-to-tenacity chain without relying on timing (which is unreliable)

```python
def capturing_wait_exponential_jitter(
    initial: float = 1,
    max: float = 4.611686018427388e18,
    exp_base: float = 2,
    jitter: float = 1,
) -> Any:
    captured_exp_base.append(exp_base)  # Capture what tenacity receives
    return original_wait_exp_jitter(initial=0, max=0, exp_base=exp_base, jitter=0)
```

### Field Mapping Verification

`test_settings_to_runtime_mapping_complete` (lines 690-722) is an excellent pattern for detecting future field orphaning bugs:

```python
# Map settings fields to their expected runtime names
expected_from_settings = {FIELD_MAPPINGS.get(f, f) for f in settings_fields}

# All settings fields must exist in config
missing = expected_from_settings - config_fields
assert not missing, (
    f"Settings fields not in RuntimeRetryConfig: {missing}. This is the P2-2026-01-21 bug pattern - add these fields!"
)
```

---

## Verdict

**PASSES AUDIT** - This is a well-designed test file. Minor issues are cosmetic. The tests use production code paths, verify database state, and include comprehensive regression tests. The approach of capturing tenacity's arguments rather than relying on timing is particularly well-considered.
