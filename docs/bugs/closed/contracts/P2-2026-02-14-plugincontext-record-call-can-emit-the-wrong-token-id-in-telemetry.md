## Summary

`PluginContext.record_call()` can emit the wrong `token_id` in telemetry because it trusts mutable `ctx.token` before the authoritative `state_id -> node_state` mapping.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — affects telemetry (ephemeral operational visibility), not Landscape audit trail (Tier 1 source of truth))

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/plugin_context.py`
- Line(s): `344-351`
- Function/Method: `PluginContext.record_call`

## Evidence

`record_call()` prefers `self.token.token_id`:

```python
if has_state:
    if self.token is not None:
        token_id = self.token.token_id
    elif self.state_id is not None:
        node_state = self.landscape.get_node_state(self.state_id)
        if node_state is not None:
            token_id = node_state.token_id
```

But `ctx.token` is explicitly "derivative state" that must be kept synchronized (`/home/john/elspeth-rapid/src/elspeth/contracts/plugin_context.py:104-106`), and engine code only sets it in one path (`/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py:226`) with no corresponding reset/authoritative validation.
Batch aggregation execution sets `ctx.state_id` and `ctx.batch_token_ids` but not `ctx.token` (`/home/john/elspeth-rapid/src/elspeth/engine/executors/aggregation.py:343-351`), while batch plugins call `ctx.record_call()` (`/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py:595-610`).

So if `ctx.token` is stale, telemetry can be attributed to the wrong token even though `state_id` is correct.

## Root Cause Hypothesis

`record_call()` uses a convenience shortcut (`ctx.token`) instead of deriving token identity from the Tier-1 authoritative parent (`state_id`/node_state), and it does not validate that `ctx.token` matches the state being recorded.

## Suggested Fix

In `record_call()`, for `has_state=True`, always resolve token from `self.landscape.get_node_state(self.state_id)` and treat mismatch/missing state as a framework bug.

Example direction:

```python
assert self.state_id is not None
node_state = self.landscape.get_node_state(self.state_id)
if node_state is None:
    raise FrameworkBugError(f"Missing node_state for state_id={self.state_id}")
token_id = node_state.token_id
if self.token is not None and self.token.token_id != token_id:
    raise FrameworkBugError(...)
```

## Impact

Telemetry correlation (`run_id` + `token_id`) can be incorrect, which breaks cross-system traceability and misleads operators during incident/debug workflows, even when Landscape audit records are correct.
