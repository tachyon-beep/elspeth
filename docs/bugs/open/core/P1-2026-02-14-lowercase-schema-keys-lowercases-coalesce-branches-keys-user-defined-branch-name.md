## Summary

`_lowercase_schema_keys()` lowercases `coalesce.branches` keys (user-defined branch names), breaking branch identity matching against `gate.fork_to` and causing false DAG validation failures.

## Severity

- Severity: major
- Priority: P1 (upgraded from P2 — actively breaks valid mixed-case fork/coalesce pipeline configurations; not defense-in-depth, this is a real failure mode)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/config.py
- Line(s): 1866-1927
- Function/Method: `_lowercase_schema_keys`

## Evidence

The lowercasing logic preserves nested keys only for `options` and `routes`, but not `branches`:

- `/home/john/elspeth-rapid/src/elspeth/core/config.py:1911-1917` (preserve only `options`/`routes`)
- `/home/john/elspeth-rapid/src/elspeth/core/config.py:1904-1905` (default lowercasing of dict keys)

Observed transformation:

```python
from elspeth.core.config import _lowercase_schema_keys
cfg = {
  "gates":[{"fork_to":["Path_A","Path_B"], "routes":{"true":"fork","false":"x"}, ...}],
  "coalesce":[{"branches":{"Path_A":"conn_a","Path_B":"conn_b"}, ...}],
}
print(_lowercase_schema_keys(cfg))
```

Output:
```text
{'gates': [... 'fork_to': ['Path_A', 'Path_B'] ...],
 'coalesce': [{'branches': {'path_a': 'conn_a', 'path_b': 'conn_b'}}]}
```

Integration mismatch:
- Gate branch names are compared exactly in DAG builder (`/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py:379-387`).
- If branch not found, graph fails (`/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py:410-417`, `430-434`).

So config loader mutates branch identity before DAG validation.

## Root Cause Hypothesis

The key-normalization function’s preservation allowlist is incomplete. `branches` is user data (identity labels), but is treated as schema-key space and lowercased.

## Suggested Fix

Update `_lowercase_schema_keys()` to preserve nested keys for `branches` the same way it does for `routes` and `options`.

Example direction:
- Treat `new_key == "branches"` as preserve-nested.
- Add regression test: mixed-case `gate.fork_to` + matching mixed-case `coalesce.branches` should survive `load_settings()` unchanged and validate.

## Impact

Valid mixed-case branch configurations fail during DAG compilation with misleading “branch not produced/destination missing” errors, despite matching user intent. This is an integration correctness bug caused in config normalization.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/config.py.md`
- Finding index in source report: 2
- Beads: pending
