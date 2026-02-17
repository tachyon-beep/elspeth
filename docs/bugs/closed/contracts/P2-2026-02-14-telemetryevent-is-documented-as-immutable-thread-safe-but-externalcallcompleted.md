## Summary

`TelemetryEvent` is documented as immutable/thread-safe, but `ExternalCallCompleted` and `FieldResolutionApplied` store mutable dict references, so payloads can mutate after emission and drift from recorded hashes.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/events.py`
- Line(s): 153, 272, 338, 339, 340, 342
- Function/Method: `TelemetryEvent` contract docs, `ExternalCallCompleted.__post_init__` (missing payload snapshot/freeze), `FieldResolutionApplied` dataclass fields

## Evidence

`events.py` claims immutability, but stores mutable dicts directly:

```python
# src/elspeth/contracts/events.py:153
Events are immutable (frozen) for thread-safety ...

# src/elspeth/contracts/events.py:272
resolution_mapping: dict[str, str]

# src/elspeth/contracts/events.py:338-340
request_payload: dict[str, Any] | None = None
response_payload: dict[str, Any] | None = None
token_usage: dict[str, int] | None = None
```

`ExternalCallCompleted.__post_init__` only validates XOR parent IDs; it does not snapshot/freeze payload dicts (`src/elspeth/contracts/events.py:342`).

This is exploitable in real flow because telemetry export is async (`src/elspeth/telemetry/manager.py:19`, `src/elspeth/telemetry/manager.py:156`, `src/elspeth/telemetry/manager.py:283`), and several producers pass live dict references directly (`src/elspeth/plugins/clients/llm.py:372`, `src/elspeth/plugins/clients/http.py:403`).

Contrast: `PluginContext` already had to add deep-copy snapshotting specifically to prevent this drift (`src/elspeth/contracts/plugin_context.py:333`).

Repro from this repo (executed): creating `ExternalCallCompleted` with `request_payload=payload`, mutating `payload` afterwards changes `event.request_payload`; `event.request_hash` no longer matches `stable_hash(event.request_payload)`.

## Root Cause Hypothesis

The contract layer relies on `frozen=True` for immutability, but frozen dataclasses do not make nested containers immutable or detached from caller references. Event classes accept mutable dict fields without defensive snapshot/freeze at construction.

## Suggested Fix

In `events.py`, enforce snapshot semantics at event construction for all mutable payload fields:

- In `ExternalCallCompleted.__post_init__`, deep-copy `request_payload`, `response_payload`, and `token_usage` (using `object.__setattr__`).
- Add similar `__post_init__` for `FieldResolutionApplied` to deep-copy `resolution_mapping`.
- Optionally change annotations to `Mapping[...]` and freeze deeply (if you want true immutability, not just detachment).

## Impact

Telemetry can report payloads that were never actually sent/received at call time, and hashes can become inconsistent with payload contents. That breaks observability integrity and makes incident/audit debugging unreliable, especially under async export timing.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/events.py.md`
- Finding index in source report: 1
- Beads: pending
