## Summary

Header display mapping collisions in `JSONSink` can silently overwrite fields (data loss) when multiple source keys map to the same output key.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/json_sink.py`
- Line(s): `533-550`
- Function/Method: `JSONSink._apply_display_headers`

## Evidence

Key remapping is done with a dict comprehension:

```python
return [{display_map.get(k, k): v for k, v in row.items()} for row in rows]
```

If mapping is non-injective (example custom config: `{"a": "X", "b": "X"}`), Python dict semantics overwrite the earlier field with the later one, silently dropping data.

There is no collision guard in this sink path. Header config validation currently checks type/mode, not uniqueness of output names (`/home/john/elspeth-rapid/src/elspeth/plugins/config_base.py:226-244`).

This is especially dangerous because sink completion records use token row data, not remapped sink row (`/home/john/elspeth-rapid/src/elspeth/engine/executors/sink.py:261-267`), so artifact content can lose fields while audit node output still shows both.

## Root Cause Hypothesis

Display header support assumes one-to-one key mapping, but the implementation does not enforce that invariant before constructing output dicts.

## Suggested Fix

Add explicit collision detection before remapping (or during config parsing for JSON sink use):

- Validate display mapping is injective for relevant fields.
- In `_apply_display_headers`, detect if two different input keys map to same output key and raise `ValueError` with both source keys and collided target key.

Add tests for duplicate custom header targets and collision failure behavior.

## Impact

Silent field loss in sink artifacts breaks data integrity and can create audit inconsistencies between recorded row content and persisted JSON output.
