## Summary

`MockClock` accepts integer `start`/`set()` values and then returns `int` from `monotonic()`, violating the `Clock` protocol’s promised `float` return type.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `/home/john/elspeth/src/elspeth/engine/clock.py`
- Line(s): 71-86, 103-117
- Function/Method: `MockClock.__init__`, `MockClock.monotonic`, `MockClock.set`

## Evidence

`Clock.monotonic()` is declared to return `float`:

```python
# /home/john/elspeth/src/elspeth/engine/clock.py:28-37
def monotonic(self) -> float:
    ...
```

But `MockClock` stores whatever numeric object it receives without normalizing it:

```python
# /home/john/elspeth/src/elspeth/engine/clock.py:80-86
if not math.isfinite(start):
    raise ValueError(...)
self._current = start

def monotonic(self) -> float:
    return self._current
```

and later:

```python
# /home/john/elspeth/src/elspeth/engine/clock.py:113-117
if not math.isfinite(value):
    raise ValueError(...)
if value < self._current:
    raise ValueError(...)
self._current = value
```

Verified behavior from the repo code path:

```python
from elspeth.engine.clock import MockClock
c1 = MockClock(start=5)
type(c1.monotonic()).__name__   # int

c2 = MockClock(start=0.0)
c2.set(42)
type(c2.monotonic()).__name__   # int
```

The existing tests miss this because they compare numeric equality rather than type after `set()`:

```python
# /home/john/elspeth/tests/unit/engine/test_clock.py:349-355
clock = MockClock()
clock.set(42)
assert clock.monotonic() == 42.0
```

So the code does not do what its protocol says: it returns `int` for some valid call patterns instead of always returning `float`.

## Root Cause Hypothesis

`MockClock` validates finiteness and monotonicity but never canonicalizes its internal state to the protocol type. Because Python does not enforce the `float` annotation at runtime, integer inputs pass through unchanged and become persistent internal state.

## Suggested Fix

Normalize all stored values to `float` at write time:

```python
self._current = float(start)
...
self._current = float(value)
```

Optionally also normalize `seconds` before arithmetic for consistency:

```python
seconds = float(seconds)
self._current += seconds
```

That keeps `MockClock.monotonic()` aligned with the `Clock` contract regardless of whether callers pass `int` or `float`.

## Impact

The main impact is contract drift in a module that is injected into timeout-sensitive engine paths such as [triggers.py](/home/john/elspeth/src/elspeth/engine/triggers.py#L52) and [coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L128). Most arithmetic still “works” because Python mixes `int` and `float`, so this is unlikely to corrupt audit state directly, but it does make the clock abstraction lie about its runtime type and can break strict type assertions, future protocol checks, or any downstream code that assumes `float`-specific behavior.
