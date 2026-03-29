## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/errors.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/errors.py
- Line(s): 17-58
- Function/Method: CAPACITY_ERROR_CODES, is_capacity_error, CapacityError.__init__

## Evidence

`/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/errors.py:17-32` defines a narrow classifier for HTTP capacity statuses:

```python
CAPACITY_ERROR_CODES: frozenset[int] = frozenset({429, 503, 529})

def is_capacity_error(status_code: int) -> bool:
    return status_code in CAPACITY_ERROR_CODES
```

`/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/errors.py:35-58` defines `CapacityError` as the retry signal used by pooled execution:

```python
class CapacityError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        if not (100 <= status_code <= 599):
            raise ValueError(...)
        super().__init__(message)
        self.status_code = status_code
        self.retryable = True
```

Integration usage is consistent with that contract:

- `/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py:274-279` only raises `CapacityError` after first checking `is_capacity_error(status_code)`.
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py:497-507` treats `CapacityError` as retryable pool backoff input and preserves `status_code` in timeout errors.
- `/home/john/elspeth/src/elspeth/engine/processor.py:1116-1141` treats `CapacityError` as retryable engine-level transient failure.
- `/home/john/elspeth/tests/unit/plugins/llm/test_capacity_errors.py:11-58` and `/home/john/elspeth/tests/unit/plugins/test_post_init_validations.py:30-71` cover the intended classifier and constructor behavior.

I did not find a mismatch where this file causes silent data loss, tier confusion, protocol breakage, or incorrect retry semantics in current in-repo call sites.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix required based on current evidence.

## Impact

No concrete breakage attributable to `/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/errors.py` was verified.
