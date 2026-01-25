# Bug Report: Gate/Sink Executions Don't Initialize PluginContext state_id

## Summary

- PluginContext for gates and sinks missing `state_id`, preventing external call recording for these plugin types.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Branch Bug Scan
- Date: 2026-01-25
- Related run/issue ID: BUG-RECORDER-01

## Evidence

- `src/elspeth/core/landscape/recorder.py` - PluginContext created without state_id for gates/sinks
- External API calls from gates/sinks cannot be recorded

## Impact

- Audit completeness: Cannot trace external calls made by gates or sinks

## Proposed Fix

```python
# Pass state_id through PluginContext for all plugin types
ctx = PluginContext(state_id=state_id, ...)
```

## Acceptance Criteria

- Gate/sink external calls recordable in call_audit table

## Tests

- New tests required: yes, test gate/sink external call recording
