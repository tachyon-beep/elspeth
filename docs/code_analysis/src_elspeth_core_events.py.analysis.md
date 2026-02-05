# Analysis: src/elspeth/core/events.py

**Lines:** 111
**Role:** Synchronous event bus for CLI observability. Publishes domain events (phase transitions, row completion, transform progress) from the orchestrator to CLI formatters for real-time display.
**Key dependencies:** No external imports (only stdlib `collections.abc`, `typing`). Imported by `src/elspeth/engine/orchestrator/core.py`, `src/elspeth/core/__init__.py`. Consumed by test files and CLI formatting layers.
**Analysis depth:** FULL

## Summary

This is a clean, minimal event bus implementation. The code is well-designed with protocol-based typing (no inheritance for `NullEventBus`), proper documentation, and deliberate design choices that align with the project's philosophy (handler exceptions propagate because formatters are "our code"). The file has no critical or security issues. There are two minor observations worth noting related to thread safety and unbounded subscriber growth.

## Warnings

### [44] Unbounded subscriber list growth with no unsubscribe mechanism

**What:** The `_subscribers` dict accumulates handlers via `subscribe()` but there is no `unsubscribe()` method and no mechanism to clear handlers.
**Why it matters:** In long-running processes or test suites that create many `EventBus` instances with subscriptions, handlers that capture closures over large objects could prevent garbage collection. More practically, if any code path subscribes in a loop (e.g., during retry logic), handlers accumulate without bound.
**Evidence:**
```python
self._subscribers: dict[type, list[Callable[[Any], None]]] = {}
# ...
self._subscribers[event_type].append(handler)  # Only grows, never shrinks
```
**Mitigating factor:** The EventBus appears to be created once per orchestrator run and discarded afterward, so this is unlikely to manifest in practice. If the orchestrator is ever used in a long-lived service mode (not just CLI), this would become relevant.

### [83-85] Not thread-safe for concurrent subscribe/emit

**What:** The `emit()` method iterates `self._subscribers.get(type(event), [])` without synchronization. If `subscribe()` is called concurrently from another thread while `emit()` is iterating, the list could be mutated during iteration.
**Why it matters:** The docstring says "synchronous event bus" and current usage is single-threaded (CLI context), but there is no guard preventing misuse in a multi-threaded context. The orchestrator does use thread pools for concurrency.
**Evidence:**
```python
def emit(self, event: T) -> None:
    handlers = self._subscribers.get(type(event), [])  # Gets reference to mutable list
    for handler in handlers:                            # Iteration over live list
        handler(event)
```
**Mitigating factor:** Current usage pattern is single-threaded. The orchestrator creates the EventBus and both subscribes and emits from the same thread. If this changes (e.g., emitting from worker threads), a `RuntimeError: list changed size during iteration` could surface.

## Observations

### [88-111] NullEventBus protocol-based design is well-reasoned

**What:** `NullEventBus` deliberately does NOT inherit from `EventBus`. It satisfies `EventBusProtocol` structurally. The docstring explicitly explains the rationale.
**Why it matters:** This is good design. If someone subscribes to a `NullEventBus` expecting callbacks, the protocol-based approach makes the no-op behavior explicit rather than hiding it behind inheritance. This aligns with the project's "defective plugin is worse than a crash" philosophy.

### [25] TypeVar T is unconstrained

**What:** `T = TypeVar("T")` is used for event types but is completely unconstrained. Any type can be used as an event, including primitives, None, or mutable objects.
**Why it matters:** Low priority. There's no base `Event` class or protocol that events must satisfy. This means `bus.emit(42)` or `bus.emit(None)` would work without error but is meaningless. Type checking at call sites would catch most misuse.

## Verdict

**Status:** SOUND
**Recommended action:** No changes required. The thread-safety note should be documented if EventBus usage ever moves to multi-threaded contexts. The lack of `unsubscribe()` is acceptable given the current lifecycle pattern.
**Confidence:** HIGH -- The file is small, has no external dependencies, and the logic is straightforward. All code paths are easy to reason about.
