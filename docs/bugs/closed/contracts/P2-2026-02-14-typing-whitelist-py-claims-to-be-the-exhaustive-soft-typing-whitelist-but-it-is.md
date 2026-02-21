## Summary

`typing_whitelist.py` claims to be the exhaustive soft-typing whitelist, but it is disconnected from enforcement and already contains stale type/location claims.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/typing_whitelist.py`
- Line(s): `4-7`, `49-58`, `121`
- Function/Method: Module-level constants (`DYNAMIC_SCHEMA_LOCATIONS`, `SERIALIZATION_BOUNDARY_LOCATIONS`)

## Evidence

`typing_whitelist.py` states it is authoritative:

- `/home/john/elspeth-rapid/src/elspeth/contracts/typing_whitelist.py:4-7` says this module documents “every place in the codebase” where soft typing is intentional.

But enforcement uses a different source of truth:

- `/home/john/elspeth-rapid/scripts/check_contracts.py:1145` hardcodes `whitelist_path = Path("config/cicd/contracts-whitelist.yaml")`.
- `rg -n "contracts\\.typing_whitelist|typing_whitelist" src scripts tests` returns only `typing_whitelist.py` itself (no consumer).

The target file is also stale vs implementation:

- `/home/john/elspeth-rapid/src/elspeth/contracts/typing_whitelist.py:49-50` says `TransformResult.row` is `dict[str, Any] | PipelineRow | None`.
- Actual type is `/home/john/elspeth-rapid/src/elspeth/contracts/results.py:107` -> `row: PipelineRow | None`.

- `/home/john/elspeth-rapid/src/elspeth/contracts/typing_whitelist.py:57-58` says `SourceRow.row` is `dict[str, Any]`.
- Actual type is `/home/john/elspeth-rapid/src/elspeth/contracts/results.py:478` -> `row: Any`.

There is also explicit repository guidance pointing to YAML, not this module:

- `/home/john/elspeth-rapid/src/elspeth/contracts/__init__.py:4-5` says internal types are whitelisted in `config/cicd/contracts-whitelist.yaml`.

## Root Cause Hypothesis

A second, manual whitelist artifact was added in `contracts/` and not wired into CI checks, so it drifted from the enforced YAML whitelist and from current type annotations.

## Suggested Fix

Make `typing_whitelist.py` non-authoritative or remove it. Primary options:

1. Delete this module and rely solely on `config/cicd/contracts-whitelist.yaml`.
2. If keeping it, rewrite it as generated/derived documentation from the YAML whitelist (or add CI asserting exact sync).
3. Immediately fix stale entries (`TransformResult.row`, `SourceRow.row`, recorder location wording) and remove the “every place in the codebase” claim unless sync is enforced.

## Impact

This creates a contract/audit documentation integrity gap: engineers can trust incorrect whitelist claims, potentially approving wrong typing exemptions or missing real drift. Runtime behavior is unaffected today, but process-level assurance (“authoritative whitelist”) is currently false.

## Triage

- Status: closed (won't fix — delete the file)
- Disposition: Not a bug. `typing_whitelist.py` is dead code with no consumers. The real enforcement lives in `config/cicd/contracts-whitelist.yaml`. Correct action is to delete the file as a cleanup chore, not fix it.
- Closed: 2026-02-14, triage review
- Source report: `docs/bugs/generated/contracts/typing_whitelist.py.md`
