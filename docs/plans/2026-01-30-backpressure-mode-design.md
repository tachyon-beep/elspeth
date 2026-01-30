# Backpressure Mode Implementation Design

**Date:** 2026-01-30
**Issue:** elspeth-rapid-ceq
**Status:** Ready for implementation

## Problem Statement

The `backpressure_mode` configuration field is orphaned - validated in `TelemetrySettings` but never used at runtime. Users can configure `backpressure_mode: drop` expecting behavior changes, but the setting is silently ignored.

This is the P2-2026-01-21 config orphaning pattern: config fields that pass validation but have no effect at runtime.

## Solution Overview

Decouple event production from export via a bounded queue with a background export thread. The `backpressure_mode` setting controls queue behavior when full:

- **BLOCK:** `queue.put()` blocks until space available (pipeline slows)
- **DROP:** `queue.put_nowait()` drops event on `queue.Full` (pipeline unaffected)

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│ Pipeline Thread │────▶│ Queue        │────▶│ Export Thread   │
│                 │     │ maxsize=1000 │     │                 │
│ handle_event()  │     │              │     │ _export_loop()  │
│ - filter        │     │ BLOCK: wait  │     │ - get event     │
│ - enqueue       │     │ DROP: drop   │     │ - export to all │
│ - return fast   │     │              │     │ - track metrics │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

## Detailed Design

### TelemetryManager Changes

```python
import queue
import threading
from elspeth.contracts.enums import BackpressureMode

class TelemetryManager:
    def __init__(self, config, exporters):
        # Existing initialization...
        self._config = config
        self._exporters = exporters

        # New: Queue and background thread
        self._queue: queue.Queue[TelemetryEvent | None] = queue.Queue(maxsize=1000)
        self._dropped_lock = threading.Lock()
        self._shutdown = False

        # Start export thread
        self._export_thread = threading.Thread(
            target=self._export_loop,
            name="telemetry-export",
            daemon=True,
        )
        self._export_thread.start()

    def handle_event(self, event: TelemetryEvent) -> None:
        """Queue event for async export."""
        if self._disabled or self._shutdown:
            return
        if not self._exporters:
            return
        if not should_emit(event, self._config.granularity):
            return

        if self._config.backpressure_mode == BackpressureMode.DROP:
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                with self._dropped_lock:
                    self._events_dropped += 1
                    self._log_drops_if_needed()
        else:  # BLOCK (default)
            self._queue.put(event)

    def _export_loop(self) -> None:
        """Background thread: consume queue and export."""
        while True:
            event = self._queue.get()
            try:
                if event is None:  # Shutdown sentinel
                    break
                self._dispatch_to_exporters(event)
            finally:
                self._queue.task_done()

    def _dispatch_to_exporters(self, event: TelemetryEvent) -> None:
        """Export to all exporters with failure isolation."""
        # Existing exporter dispatch logic moves here
        failures = 0
        for exporter in self._exporters:
            try:
                exporter.export(event)
            except Exception as e:
                failures += 1
                self._exporter_failures[exporter.name] = (
                    self._exporter_failures.get(exporter.name, 0) + 1
                )
                logger.warning(...)

        # Update metrics (single-threaded in export loop)
        if failures == 0:
            self._events_emitted += 1
            self._consecutive_total_failures = 0
        elif failures == len(self._exporters):
            self._consecutive_total_failures += 1
            self._events_dropped += 1  # No lock needed - only export thread writes
            # ... existing failure handling ...
        else:
            self._events_emitted += 1
            self._consecutive_total_failures = 0

    def flush(self) -> None:
        """Wait for queue to drain, then flush exporters."""
        self._queue.join()
        for exporter in self._exporters:
            try:
                exporter.flush()
            except Exception as e:
                logger.warning(...)

    def close(self) -> None:
        """Shutdown export thread and close exporters."""
        self._shutdown = True
        self._queue.put(None)  # Sentinel to stop export loop
        self._export_thread.join(timeout=5.0)

        # Drain any remaining events (best effort)
        while True:
            try:
                event = self._queue.get_nowait()
                if event is not None:
                    self._dispatch_to_exporters(event)
                self._queue.task_done()
            except queue.Empty:
                break

        # Close exporters
        logger.info("Telemetry manager closing", **self.health_metrics)
        for exporter in self._exporters:
            try:
                exporter.close()
            except Exception as e:
                logger.warning(...)
```

### Thread Safety

| Component | Access Pattern | Protection |
|-----------|----------------|------------|
| `_events_dropped` | Both threads (DROP mode) | `_dropped_lock` |
| `_events_emitted` | Export thread only | None needed |
| `_exporter_failures` | Export thread only | None needed |
| `_consecutive_total_failures` | Export thread only | None needed |
| `_queue` | Both threads | `queue.Queue` is thread-safe |

### Configuration

Queue size is an internal default (not user-configurable):

```python
# contracts/config/defaults.py
INTERNAL_DEFAULTS = {
    # ... existing ...
    "telemetry": {
        "queue_size": 1000,
    },
}
```

1000 events is generous for the backpressure buffer. If tuning is needed, we can expose it later (YAGNI).

### Graceful Shutdown

1. Set `_shutdown = True` to reject new events
2. Send `None` sentinel to stop export loop
3. Join thread with timeout (5s)
4. Drain remaining queue items (best effort)
5. Close all exporters

### API Compatibility

| Method | Before | After |
|--------|--------|-------|
| `handle_event(event)` | Synchronous, blocks on export | Non-blocking (queues) |
| `flush()` | Flushes exporters | Drains queue + flushes exporters |
| `close()` | Closes exporters | Stops thread + drains + closes |
| `health_metrics` | Returns dict | Same (thread-safe reads) |

## Files to Modify

| File | Changes |
|------|---------|
| `src/elspeth/telemetry/manager.py` | Add queue, background thread, backpressure logic |
| `src/elspeth/contracts/config/defaults.py` | Add `telemetry.queue_size` internal default |
| `tests/telemetry/test_manager.py` | Add backpressure mode tests |

## Test Plan

### Unit Tests

1. **DROP mode drops on full queue**
   - Fill queue to capacity with slow exporter
   - Verify `handle_event()` returns immediately
   - Verify `_events_dropped` increments
   - Verify pipeline thread doesn't block

2. **BLOCK mode blocks on full queue**
   - Fill queue to capacity
   - Verify `handle_event()` blocks (test with timeout)
   - Drain one item from queue
   - Verify `handle_event()` unblocks

3. **Graceful shutdown drains queue**
   - Queue several events
   - Call `close()`
   - Verify all events were exported before return

4. **Shutdown timeout doesn't hang**
   - Create exporter that blocks forever
   - Call `close()`
   - Verify returns within reasonable time (timeout + buffer)

### Integration Tests

1. **Config wiring**
   - Configure `backpressure_mode: drop`
   - Verify DROP behavior

2. **Config wiring**
   - Configure `backpressure_mode: block`
   - Verify BLOCK behavior

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Thread leak on exception | Low | Medium | Daemon thread + explicit join |
| Lost events on crash | Medium | Low | Best-effort drain; telemetry is ephemeral |
| Metrics race condition | Low | Low | Lock on shared counter |
| Deadlock in close() | Low | High | Timeout on join, drain with get_nowait |

## Alternatives Considered

### A. Timeout-based inline export
Keep synchronous export but timeout after N ms in DROP mode. Rejected because you can't timeout a synchronous HTTP call mid-flight without async.

### B. Remove DROP mode entirely
Simplest option - just don't support it. Rejected because the config already claims to support it (`_IMPLEMENTED_BACKPRESSURE_MODES` includes DROP).

### C. Use BoundedBuffer for backpressure
The existing `BoundedBuffer` is for exporter-level batching, not manager-level backpressure. Using it would conflate two concerns.

## Implementation Notes

- Use `queue.Queue` from stdlib (thread-safe, blocking semantics built-in)
- Thread should be daemon so it exits with process
- Use `queue.task_done()` / `queue.join()` for flush semantics
- Sentinel value `None` signals shutdown (distinct from any real event)
