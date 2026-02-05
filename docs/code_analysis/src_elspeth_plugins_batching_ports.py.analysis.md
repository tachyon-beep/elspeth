# Analysis: src/elspeth/plugins/batching/ports.py

**Lines:** 83
**Role:** Defines the `OutputPort` protocol (the interface for receiving results from upstream pipeline stages) and two concrete implementations: `NullOutputPort` (discards results) and `CollectorOutputPort` (collects results into a list for testing). This is the central abstraction that decouples transforms from their downstream consumers.
**Key dependencies:** TYPE_CHECKING imports only (`ExceptionResult`, `TransformResult`, `TokenInfo`). Imported by `mixin.py`, `__init__.py`, all production batch transforms (azure.py, azure_multi_query.py, openrouter.py, etc.), `batch_adapter.py`, and test files.
**Analysis depth:** FULL

## Summary

This is a clean, minimal protocol definition file. The `OutputPort` protocol is well-designed with correct use of `@runtime_checkable` for structural typing. The two concrete implementations are straightforward. One warning-level finding was identified: `CollectorOutputPort` is not thread-safe but is used in tests where `emit()` is called from a background release thread. No critical findings.

## Warnings

### [68-83] CollectorOutputPort is not thread-safe but used in multi-threaded test scenarios

**What:** `CollectorOutputPort.emit()` appends to `self.results` (a plain Python list) without any synchronization. In the test suite (`test_batch_transform_mixin.py`), this port is passed to `BatchTransformMixin.init_batch_processing()` as the output port. The mixin's release thread (a background `threading.Thread`) calls `emit()` on this port, while the test's main thread reads `collector.results` after `flush_batch_processing()`.

**Why it matters:** In CPython, list.append() is effectively atomic due to the GIL, and the test pattern (write from release thread, then read from main thread after flush) has an implicit happens-before relationship via `flush_batch_processing()` which polls `pending_count` until zero. So in practice this works correctly. However:

1. The code relies on CPython implementation details (GIL atomicity of list.append), not on the Python language specification.
2. If the project ever moves to a GIL-free Python (PEP 703 / free-threaded Python 3.13+), this would become a data race.
3. There is no memory barrier between the release thread's last `emit()` and the test thread's `collector.results` read -- the `flush_batch_processing()` poll loop provides an implicit barrier via lock acquisition in `pending_count`, but this is fragile and not documented.

**Evidence:**
```python
class CollectorOutputPort:
    def __init__(self) -> None:
        self.results: list[...] = []  # No lock

    def emit(self, token, result, state_id) -> None:
        self.results.append((token, result, state_id))  # No lock

# In test:
transform.flush_batch_processing(timeout=10.0)
assert len(collector.results) == 3  # Reads list written by release thread
```

The production output port (`SharedBatchAdapter` in `batch_adapter.py`) correctly uses a threading.Lock, so this is isolated to the test utility.

## Observations

### [26-54] OutputPort is a runtime_checkable Protocol

**What:** The `@runtime_checkable` decorator allows `isinstance(obj, OutputPort)` checks at runtime. This is used in the codebase to validate that output ports conform to the protocol.

**Why it matters:** This is good practice. The protocol has a single method (`emit`), so the runtime check verifies the method exists. The type signature is only checked by static type checkers (mypy), not at runtime.

### [57-65] NullOutputPort silently discards all results

**What:** `NullOutputPort.emit()` has an empty body (`pass`). This is explicitly documented as "useful for testing or when results should be dropped."

**Why it matters:** This is intentional and correct for its stated use case. However, in a system where "no silent drops" is a principle, the existence of a discard port is worth noting. The production code does not use `NullOutputPort` -- only `SharedBatchAdapter` is used in production, and `CollectorOutputPort`/`NullOutputPort` are testing utilities.

### [40] emit() accepts TransformResult | ExceptionResult union

**What:** The `emit()` protocol accepts both `TransformResult` and `ExceptionResult` in the `result` parameter. This is the mechanism by which plugin exceptions propagate through the async pipeline.

**Why it matters:** This is well-designed. The `ExceptionResult` variant allows the mixin's release loop (mixin.py line 295-300) to forward exception information to the waiter, which then re-raises it in the orchestrator thread. The protocol correctly documents this dual usage.

### [74-79] CollectorOutputPort stores tuples with state_id

**What:** The results list stores the full `(token, result, state_id)` tuple, enabling tests to verify retry-safe result routing.

**Why it matters:** Good test design -- the collector captures all information needed to verify the mixin's behavior, including the state_id for retry correctness assertions.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a threading.Lock to `CollectorOutputPort` for future-proofing against free-threaded Python, or document the CPython GIL dependency explicitly. This is low priority since the class is test-only and the current usage pattern is safe under CPython.
**Confidence:** HIGH -- The file is 83 lines with three simple classes. All consumers were identified and analyzed.
