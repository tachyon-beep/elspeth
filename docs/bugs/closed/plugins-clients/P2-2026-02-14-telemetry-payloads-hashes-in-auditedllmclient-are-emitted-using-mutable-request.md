## Summary

Telemetry payloads/hashes in `AuditedLLMClient` are emitted using mutable request/response objects without snapshotting, so queued async export can observe mutated data that no longer matches call-time hashes.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py
- Line(s): 295-301, 359-375, 422-437
- Function/Method: `AuditedLLMClient.chat_completion`

## Evidence

`request_data` is built with direct references (`messages`, `**kwargs`) and passed directly into telemetry payload/hash fields:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py:295-301
request_data = {
    "model": model,
    "messages": messages,
    ...
    **kwargs,
}
```

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py:370-373
request_hash=stable_hash(request_data),
response_hash=stable_hash(response_data),
request_payload=request_data,
response_payload=response_data,
```

Telemetry is exported asynchronously via queue/background thread:

```python
# /home/john/elspeth-rapid/src/elspeth/telemetry/manager.py:7,62,130,156
# "Queues events for async export via background thread"
```

The project already fixed this exact drift class in `PluginContext.record_call` using deep-copy snapshots:

```python
# /home/john/elspeth-rapid/src/elspeth/contracts/plugin_context.py:333-335
request_snapshot = copy.deepcopy(request_data)
response_snapshot = copy.deepcopy(response_data) if response_data is not None else None
```

And regression tests exist for immutability/hash alignment there:

- `/home/john/elspeth-rapid/tests/unit/plugins/test_context.py:572-667`

## Root Cause Hypothesis

`AuditedLLMClient` missed the payload snapshot hardening that was added to `PluginContext.record_call`, so it still emits mutable structures directly into async telemetry flow.

## Suggested Fix

Before telemetry emission in both success and error branches:

- `request_snapshot = copy.deepcopy(request_data)`
- `response_snapshot = copy.deepcopy(response_data)` (when present)
- Compute telemetry hashes from snapshots.
- Emit `request_payload`/`response_payload` from snapshots.
- Derive `token_usage` from `response_snapshot`.

## Impact

- Telemetry payload can drift from call-time data/hashes.
- Debugging and observability correlation become unreliable.
- Operational telemetry may disagree with Landscape record timing/content.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/clients/llm.py.md`
- Finding index in source report: 2
- Beads: pending
