## Summary

`register_node()` allows implicit determinism by defaulting to `Determinism.DETERMINISTIC`, which can silently misclassify plugin behavior in the audit trail.

**CLOSED -- False positive.** Sole production caller (orchestrator/core.py:1113-1123) always provides explicit determinism= argument. Default value is never used.

## Severity

- Severity: major
- Priority: CLOSED (false positive — sole caller always provides explicit value)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_graph_recording.py`
- Line(s): 53, 42-57
- Function/Method: `register_node`

## Evidence

`register_node()` currently has a default:

```python
determinism: Determinism = Determinism.DETERMINISTIC,
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_graph_recording.py:53`)

But project contracts explicitly require no implicit determinism:
- `/home/john/elspeth-rapid/src/elspeth/contracts/enums.py:95-97` (“No default. Undeclared determinism = crash at registration time.”)

Downstream logic uses stored determinism to compute reproducibility grade:
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/reproducibility.py:39-47`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/reproducibility.py:80-95`

So an omitted determinism can be recorded as deterministic and incorrectly influence reproducibility/audit claims.

## Root Cause Hypothesis

A convenience default was introduced in recorder API, but it conflicts with the audit contract that determinism must be explicitly declared.

## Suggested Fix

Make determinism required in `register_node()` (remove the default), and fail fast if not provided.

Example direction:

```python
def register_node(..., determinism: Determinism, ...):
    ...
```

If needed, add a targeted test asserting missing determinism raises at call time.

## Impact

Incorrect determinism attribution can produce wrong reproducibility grades and misleading audit records (claims of deterministic behavior where none was declared).

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_graph_recording.py.md`
- Finding index in source report: 1
- Beads: pending
