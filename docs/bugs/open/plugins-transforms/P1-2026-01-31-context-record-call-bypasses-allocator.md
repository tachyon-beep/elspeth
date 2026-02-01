# Bug Report: PluginContext.record_call bypasses centralized call_index allocation

## Summary

- `PluginContext.record_call()` uses its own `_call_index` counter instead of delegating to `LandscapeRecorder.allocate_call_index()`. If a transform mixes `ctx.record_call()` with audited clients, duplicate `(state_id, call_index)` values can occur.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/plugins/context.py:284-295` - `record_call()` uses a local `_call_index` counter when `state_id` is set, bypassing the recorder allocator.
- `src/elspeth/core/landscape/recorder.py:1800-1821` - `allocate_call_index()` is documented as the single source of truth for `(state_id, call_index)` uniqueness.
- Recorder docstring: "All AuditedClient instances MUST delegate to this method rather than maintaining their own counters"

## Impact

- User-facing impact: IntegrityError on calls table if mixing record_call with audited clients
- Data integrity / security impact: Duplicate call_index values corrupt audit trail
- Performance or cost impact: None

## Root Cause Hypothesis

- `PluginContext` maintains its own counter instead of using the centralized allocator, violating the documented contract.

## Proposed Fix

- Code changes:
  - Change `record_call()` to use `self._recorder.allocate_call_index(state_id)` instead of local counter
  - Remove `_call_index` attribute from PluginContext
- Tests to add/update:
  - Add test that interleaves `ctx.record_call()` with audited client calls, verify no duplicate indices

## Acceptance Criteria

- All call_index values come from centralized allocator
- No duplicate `(state_id, call_index)` pairs possible

## Verification (2026-02-01)

**Status: STILL VALID**

- `PluginContext.record_call()` still increments its own `_call_index` instead of calling `allocate_call_index()`. (`src/elspeth/plugins/context.py:284-295`, `src/elspeth/core/landscape/recorder.py:1800-1821`)
