## Summary

`update_checkpoint()` does not actually update the active restored checkpoint path, so updates can be lost after resume.

## Severity

- Severity: major
- Priority: P1 (upgraded from P2 — checkpoint correctness is critical for resume; stale checkpoint data causes incorrect retry/recovery behavior)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/plugin_context.py`
- Line(s): `166-173`, `175-184`
- Function/Method: `PluginContext.get_checkpoint`, `PluginContext.update_checkpoint`

## Evidence

`get_checkpoint()` prioritizes restored checkpoint data in `_batch_checkpoints[node_id]`:

```python
if self.node_id and self.node_id in self._batch_checkpoints:
    restored = self._batch_checkpoints[self.node_id]
    if restored:
        return restored
return self._checkpoint if self._checkpoint else None
```

But `update_checkpoint()` always writes only to `_checkpoint`:

```python
self._checkpoint.update(data)
```

So when a restored checkpoint exists, subsequent `get_checkpoint()` keeps returning the old restored dict, not the newly updated local dict. This contradicts the method contract text (“Merges the provided data into the existing checkpoint.”).

## Root Cause Hypothesis

Two checkpoint stores are used (restored per-node and local), but `update_checkpoint()` only mutates one, while `get_checkpoint()` reads from the other first.

## Suggested Fix

Make `update_checkpoint()` update whichever checkpoint is currently authoritative for the node (restored entry when present, otherwise local), or normalize to a single active checkpoint dict for the current node.

Example direction:

```python
if self.node_id and self.node_id in self._batch_checkpoints and self._batch_checkpoints[self.node_id]:
    self._batch_checkpoints[self.node_id].update(data)
else:
    self._checkpoint.update(data)
```

## Impact

Resume flows that need to evolve checkpoint contents can silently keep stale checkpoint data, causing incorrect retry/checkpoint persistence behavior and harder recovery debugging.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/plugin_context.py.md`
- Finding index in source report: 2
- Beads: pending
