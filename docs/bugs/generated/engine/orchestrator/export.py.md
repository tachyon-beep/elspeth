## Summary

`export_landscape()` reuses a sink instance after the orchestrator has already run that sink’s `on_complete()` and `close()`, so post-run export can write through a finalized/closed sink or trigger a second close on cleanup.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/engine/orchestrator/export.py`
- Line(s): 91-116
- Function/Method: `export_landscape`

## Evidence

`export_landscape()` builds a context and writes directly to the configured sink:

```python
recorder = LandscapeRecorder(db)
ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
...
if records:
    _artifact_descriptor = sink.write(records, ctx)
sink.flush()
...
sink.close()
```

Source: `/home/john/elspeth/src/elspeth/engine/orchestrator/export.py:91-116`

But the main run path cleans up all sinks before the export phase even starts:

```python
finally:
    self._cleanup_plugins(config, run_ctx.ctx, include_source=True)
...
if settings is not None and settings.landscape.export.enabled:
    self._execute_export_phase(recorder, run.run_id, settings, config)
```

Source: `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:2555-2556` and `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1196-1198`

And `_cleanup_plugins()` does both `on_complete()` and `close()` on every sink in `config.sinks`, including the export sink that was excluded only from the execution graph:

```python
for sink in config.sinks.values():
    sink.on_complete(ctx)
...
for sink in config.sinks.values():
    sink.close()
```

Source: `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:690-718`

This is not harmless for all sinks. `ChromaSink.write()` explicitly requires `on_start()` state to still be live:

```python
if self._collection is None:
    raise FrameworkBugError("ChromaSink._collection is None — on_start() was not called before write()")
```

and `close()` clears that state:

```python
self._client = None
self._collection = None
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:187-190` and `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:462-466`

So the current flow is: `on_start()` during run setup, then `on_complete()/close()` in `_cleanup_plugins()`, then `export_landscape()` tries to write with the same sink object after teardown.

## Root Cause Hypothesis

The export path assumes the configured export sink is still open and available after pipeline execution. In reality, the orchestrator treats that sink like every other sink for lifecycle teardown, then `export.py` reuses the torn-down instance as if it were fresh. The target file is missing export-specific lifecycle ownership.

## Suggested Fix

`export.py` should not write through a sink instance that belongs to the already-cleaned-up pipeline lifecycle.

A safe fix in this file is to give export its own sink lifecycle:
1. Re-instantiate a fresh sink from the configured sink class/config for export.
2. Call `on_start()` with a proper lifecycle context before any write.
3. Perform write/flush.
4. Call `on_complete()` and `close()` exactly once for that export-owned instance.

At minimum, `export.py` must stop calling `close()` on the shared pipeline sink if the orchestrator still owns that instance.

## Impact

Successful runs can fail during the export phase depending on sink type, especially sinks that allocate resources in `on_start()` and clear them in `close()`. This breaks post-run audit export and can also produce spurious cleanup failures from double-closing the same sink. The failure is in the audit-export path itself, so it directly undermines the “completed run can always be exported” expectation.
---
## Summary

`export_landscape()` passes export sinks a `PluginContext` with no `operation_id`, so any sink that records external calls via `ctx.record_call()` crashes and loses operation-level audit lineage during export.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/engine/orchestrator/export.py`
- Line(s): 91-113
- Function/Method: `export_landscape`

## Evidence

The export path constructs the sink context like this:

```python
recorder = LandscapeRecorder(db)
ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
...
_artifact_descriptor = sink.write(records, ctx)
```

Source: `/home/john/elspeth/src/elspeth/engine/orchestrator/export.py:91-113`

That context sets neither `state_id` nor `operation_id`. But `PluginContext.record_call()` enforces that exactly one of them must be set:

```python
if not has_state and not has_operation:
    raise FrameworkBugError(
        f"record_call() called without state_id or operation_id. "
        ...
    )
```

Source: `/home/john/elspeth/src/elspeth/contracts/plugin_context.py:233-249`

Several sink implementations always call `ctx.record_call()` for their external writes.

Examples:

`DatabaseSink` records DDL and INSERT calls:

```python
ctx.record_call(
    call_type=CallType.SQL,
    status=CallStatus.SUCCESS,
    request_data={"operation": "INSERT", "table": self._table_name, "row_count": len(rows)},
    ...
)
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/database_sink.py:516-529`

`AzureBlobSink` records upload calls:

```python
ctx.record_call(
    call_type=CallType.HTTP,
    status=CallStatus.SUCCESS,
    request_data={"operation": "upload_blob", ...},
    ...
)
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py:642-658`

`DataverseSink` also records HTTP calls through the sink context:

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/dataverse.py:393-423`

So exporting to any sink that correctly audits its own external I/O will fail immediately with a framework bug because `export.py` never creates an export operation parent.

## Root Cause Hypothesis

The normal sink execution path gives sink writes an operation-scoped context, but `export.py` bypasses that machinery and hand-rolls a minimal `PluginContext`. That shortcut omits the operation parent required for source/sink call attribution, breaking the audit contract for external export writes.

## Suggested Fix

Before calling `sink.write()`, `export.py` should create an operation record for the export write and set `ctx.operation_id` to that operation’s ID. After the write finishes, it should complete that operation with success or failure status.

The fix belongs in `export.py` because this file is the code constructing the ad hoc sink context and bypassing the normal operation lifecycle.

## Impact

Exporting to sinks that correctly record their external calls can fail outright. Even if a sink happens not to call `ctx.record_call()`, the export path currently has no operation-level lineage for the export write itself, which leaves the audit trail incomplete for external export side effects.
