## Summary

`get_source_schema()` coerces Tier-1 DB values with `str(...)`, masking type corruption instead of crashing immediately.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — str() on already-string value is a no-op; near-zero practical risk)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_run_recording.py`
- Line(s): 183-191
- Function/Method: `get_source_schema`

## Evidence

After null-checking, method returns `str(source_schema_json)` (`_run_recording.py:191`) rather than enforcing stored type.
Per trust model, Landscape/audit data is Tier 1 and must not be coerced (`CLAUDE.md:25-33`, `CLAUDE.md:185-190`).

Downstream resume expects valid JSON text (`src/elspeth/engine/orchestrator/core.py:1886` uses `json.loads(source_schema_json)`), so coercion can transform corruption into a later, less actionable parse failure.

## Root Cause Hypothesis

A convenience cast was used to satisfy the return type annotation, but it violates Tier-1 strictness by converting unexpected DB types instead of treating them as integrity failures.

## Suggested Fix

Replace coercion with strict type enforcement:

- If `type(source_schema_json) is not str`, raise `AuditIntegrityError` (or `ValueError`) including the actual type.
- Return `source_schema_json` unchanged when valid.

## Impact

Corrupted schema storage can be silently normalized and fail later with poorer diagnostics, weakening immediate audit-integrity detection.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_run_recording.py.md`
- Finding index in source report: 3
- Beads: pending

Triage: Downgraded P2→P3. SQLAlchemy returns Python str from TEXT column. The str() call is redundant but harmless. Principle violation is real but practical risk approaches zero.
