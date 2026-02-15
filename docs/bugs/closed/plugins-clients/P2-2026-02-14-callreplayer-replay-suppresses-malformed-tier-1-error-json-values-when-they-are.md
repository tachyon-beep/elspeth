## Summary

`CallReplayer.replay()` suppresses malformed Tier-1 `error_json` values when they are empty-string/falsey, instead of crashing on audit data corruption.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py
- Line(s): 205-207
- Function/Method: `CallReplayer.replay`

## Evidence

Current code:

```python
error_data: dict[str, Any] | None = None
if call.error_json:
    error_data = json.loads(call.error_json)
```

(`/home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py:205-207`)

This truthy check treats `""` as “no error payload” and skips parsing. Per project policy, Landscape data is Tier 1 and anomalies must crash, not be silently ignored (`CLAUDE.md:25-34`).

Recorder emits either canonical JSON string or `None`:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:150`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:163`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:375`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:388`

So empty string is invalid/corrupt Tier-1 data and should not be masked.

## Root Cause Hypothesis

A truthiness guard (`if call.error_json`) was used instead of an explicit null check (`is not None`), which unintentionally converts malformed falsey values into silent “missing” error metadata.

## Suggested Fix

Use strict null semantics:

```python
if call.error_json is not None:
    error_data = json.loads(call.error_json)
```

This preserves fail-fast behavior for malformed Tier-1 data (`""`, invalid JSON).

## Impact

Corrupt audit rows can be replayed without surfacing corruption, and error lineage can be silently dropped from replay results, weakening audit integrity guarantees.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/clients/replayer.py.md`
- Finding index in source report: 2
- Beads: pending
