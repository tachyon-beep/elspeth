## Summary

Plugin startup failures leak resources because `Orchestrator._initialize_run_context()` calls plugin `on_start()` hooks before entering the cleanup path, so a later `on_start()` exception skips `on_complete()` and `close()` entirely.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/orchestrator/core.py
- Line(s): 1558-1593
- Function/Method: `_initialize_run_context`

## Evidence

`_initialize_run_context()` runs startup hooks first:

```python
if include_source_on_start:
    config.source.on_start(ctx)
for transform in config.transforms:
    transform.on_start(ctx)
for sink in config.sinks.values():
    sink.on_start(ctx)
```

Only `_build_processor(...)` is wrapped in cleanup logic:

```python
try:
    processor, coalesce_node_map, coalesce_executor = self._build_processor(...)
except Exception:
    self._cleanup_plugins(config, ctx, include_source=include_source_on_start)
    raise
```

That means any exception from `source.on_start`, `transform.on_start`, or `sink.on_start` exits before `_cleanup_plugins()` is called. The file even notes this at [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1561): `on_start` is outside the cleanup `try/finally`.

This is not theoretical. `RAGTransform.on_start()` constructs a provider, records readiness, and can then raise `RetrievalNotReadyError` if the collection is empty/unreachable at [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L119) and [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L151). Its resource release lives in `close()` at [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L315). So a readiness failure leaves the provider unclosed.

Existing cleanup tests cover success, source-load failure, and `close()` failure, but not `on_start()` failure; see [test_orchestrator_cleanup.py](/home/john/elspeth/tests/integration/pipeline/orchestrator/test_orchestrator_cleanup.py#L68) and [test_orchestrator_cleanup.py](/home/john/elspeth/tests/integration/pipeline/orchestrator/test_orchestrator_cleanup.py#L147).

## Root Cause Hypothesis

The orchestrator treats startup hooks as if they cannot fail after allocating resources, then only added cleanup around processor construction. That leaves a gap between partial plugin initialization and teardown.

## Suggested Fix

Move plugin startup into the same guarded region as processor construction, and always run cleanup for plugins whose startup has begun.

A safe pattern is:

```python
started = False
try:
    if include_source_on_start:
        config.source.on_start(ctx)
    for transform in config.transforms:
        transform.on_start(ctx)
    for sink in config.sinks.values():
        sink.on_start(ctx)
    started = True

    processor, coalesce_node_map, coalesce_executor = self._build_processor(...)
except Exception:
    if started:
        self._cleanup_plugins(config, ctx, include_source=include_source_on_start)
    else:
        self._cleanup_plugins(config, ctx, include_source=include_source_on_start)
    raise
```

Better still, track which plugins successfully started and only call `on_complete()/close()` for that subset. Add an integration test where a transform’s `on_start()` allocates a resource and then raises.

## Impact

A startup failure can leak network clients, file handles, provider objects, or thread-pool resources. It also violates the orchestrator’s lifecycle contract by leaving partially initialized plugins without terminal cleanup.
---
## Summary

`resume()` has an early-exit success path that finalizes the run and deletes checkpoints but skips both `RunFinished` telemetry and the `RunSummary` event, making that completion path invisible to observability consumers.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/engine/orchestrator/core.py
- Line(s): 2691-2706
- Function/Method: `resume`

## Evidence

The early-exit branch is:

```python
if not unprocessed_rows and not restored_state and restored_coalesce_state is None:
    recorder.finalize_run(run_id, status=RunStatus.COMPLETED)
    self._delete_checkpoints(run_id)
    return RunResult(...)
```

In this branch, `resume()` returns before the normal completion ceremony at [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2738), which emits `RunFinished` telemetry and `RunSummary`.

By contrast, the normal success path does all three:

- `finalize_run(...)` at [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2738)
- `_emit_telemetry(RunFinished(...))` at [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2743)
- `_events.emit(RunSummary(...))` at [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2755)

The same pattern exists in `run()` at [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1176) and [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1202).

The early-exit regression test only asserts checkpoint deletion and zero processed rows; it does not assert `RunFinished` or `RunSummary` emission, so this gap is currently untested at [test_resume_comprehensive.py](/home/john/elspeth/tests/integration/pipeline/test_resume_comprehensive.py#L341).

## Root Cause Hypothesis

The earlier bug fix for the early-exit path focused on checkpoint cleanup and returned immediately after that fix, bypassing the shared completion ceremony used everywhere else.

## Suggested Fix

Route the early-exit case through the same completion ceremony as the normal success path. At minimum, after `finalize_run(...)` emit:

```python
self._emit_telemetry(RunFinished(...))
self._events.emit(RunSummary(...))
```

using zero row counts. Add an integration test that resumes a fully processed run and asserts both `RunFinished` telemetry and a `RunSummary(COMPLETED)` event.

## Impact

Dashboards, exporters, and CLI/event-bus consumers can miss the fact that a resume finished successfully on this path. The audit DB is correct, but operational observability loses the terminal lifecycle signal for that run.
