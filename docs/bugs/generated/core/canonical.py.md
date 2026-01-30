# Bug Report: Deprecated compute_upstream_topology_hash violates no-legacy policy

## Summary

- canonical.py retains a deprecated upstream topology hashing function “kept for backwards compatibility,” which is explicitly prohibited by the repository’s No Legacy Code Policy.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of /home/john/elspeth-rapid/src/elspeth/core/canonical.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Open `src/elspeth/core/canonical.py`.
2. Locate `compute_upstream_topology_hash` and its docstring stating it is kept for backwards compatibility.

## Expected Behavior

- No backwards compatibility or deprecated/legacy functions remain in the codebase; old paths are removed and callers are updated.

## Actual Behavior

- `compute_upstream_topology_hash` is retained explicitly “for backwards compatibility,” violating the No Legacy Code Policy.

## Evidence

- `src/elspeth/core/canonical.py:214-224` (docstring: “kept for backwards compatibility”).
- `CLAUDE.md:797-834` (No Legacy Code Policy forbids backwards compatibility code and requires removing old code).

## Impact

- User-facing impact: Potential for engineers to keep or reintroduce upstream-only checkpoint hashing paths that are explicitly deprecated.
- Data integrity / security impact: Increases risk of using the weaker upstream-only hash, which can miss topology changes in multi-sink DAGs.
- Performance or cost impact: Minimal; primarily architectural/policy risk.

## Root Cause Hypothesis

- The deprecated function was left in place to preserve older usages, despite the strict policy against compatibility shims.

## Proposed Fix

- Code changes (modules/files):
  - Remove `compute_upstream_topology_hash` from `src/elspeth/core/canonical.py`.
  - Update any references (e.g., tests) to use `compute_full_topology_hash` or a properly named non-legacy helper if truly required.
- Config or schema changes: None.
- Tests to add/update:
  - Update `tests/core/checkpoint/test_manager.py` to use `compute_full_topology_hash` or the new intended API.
- Risks or migration steps:
  - Ensure no production code depends on the deprecated function (currently appears test-only).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:797-834` (No Legacy Code Policy).
- Observed divergence: Deprecated compatibility function retained in core canonical module.
- Reason (if known): Likely kept to avoid updating older tests or call sites.
- Alignment plan or decision needed: Remove deprecated function and update all call sites in the same change.

## Acceptance Criteria

- `compute_upstream_topology_hash` is removed from `src/elspeth/core/canonical.py`.
- No references to the deprecated function remain (tests updated).
- Checkpoint hashing uses full topology hashing exclusively.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_manager.py`
- New tests required: no, update existing tests

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (No Legacy Code Policy)
