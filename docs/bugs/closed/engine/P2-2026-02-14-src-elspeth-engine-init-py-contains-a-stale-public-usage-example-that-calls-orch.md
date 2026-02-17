## Summary

`src/elspeth/engine/__init__.py` contains a stale public usage example that calls `Orchestrator.run(config)` without required arguments, causing immediate runtime failure if followed.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/__init__.py`
- Line(s): `11-24` (failing call at `24`)
- Function/Method: Module docstring example block

## Evidence

`src/elspeth/engine/__init__.py:24` documents:

```python
result = orchestrator.run(config)
```

But the actual API in `src/elspeth/engine/orchestrator/core.py:666-676` is:

```python
def run(
    self,
    config: PipelineConfig,
    graph: ExecutionGraph | None = None,
    ...,
    *,
    payload_store: PayloadStore,
    ...
) -> RunResult:
```

And `src/elspeth/engine/orchestrator/core.py:703-706` enforces:

```python
if graph is None:
    raise ValueError(...)
if payload_store is None:
    raise ValueError(...)
```

So the example in the target file cannot succeed as written.

## Root Cause Hypothesis

The orchestrator API evolved to require explicit `graph` and `payload_store` for audit compliance, but the package-level docstring example in `engine/__init__.py` was not updated during that contract change.

## Suggested Fix

Update the module docstring example in `src/elspeth/engine/__init__.py` to match the current required call pattern, including graph construction and payload store injection. For example:

```python
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.payload_store import FilesystemPayloadStore

graph = ExecutionGraph.from_plugin_instances(
    source=csv_source,
    transforms=[transform1, gate1],
    sinks={"default": output_sink},
)

payload_store = FilesystemPayloadStore("./payloads")
result = orchestrator.run(config, graph=graph, payload_store=payload_store)
```

## Impact

Developers following the package’s top-level example will hit a `ValueError` immediately, creating onboarding friction and an incorrect public API contract at the engine entrypoint. This is an integration/documentation contract violation, though it does not directly corrupt audit data.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/__init__.py.md`
- Finding index in source report: 1
- Beads: pending
