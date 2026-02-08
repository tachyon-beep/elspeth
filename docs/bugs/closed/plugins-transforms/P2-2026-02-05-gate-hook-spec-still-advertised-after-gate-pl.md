# Bug Report: Gate Hook Spec Still Advertised After Gate Plugins Were Removed

## Summary

- `elspeth_get_gates` is still defined in `hookspecs.py`, but gates are documented and implemented as config-driven system operations, not plugins. This leaves a dead hook that suggests unsupported functionality and violates the no-legacy-code policy.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit for `/home/john/elspeth-rapid/src/elspeth/plugins/hookspecs.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Review the plugin protocol contract that designates gates as system operations, not plugins.
2. Inspect `hookspecs.py` and observe that `elspeth_get_gates` is still declared.
3. Review plugin discovery and registration: gates are explicitly excluded from discovery and builtin registration, making the hook unusable.

## Expected Behavior

- Hookspecs should only advertise plugin hooks that are supported and discoverable. If gates are system operations, no gate hook should exist.

## Actual Behavior

- `hookspecs.py` still exposes `elspeth_get_gates`, while discovery and registration explicitly exclude gate plugins, creating a stale and misleading contract.

## Evidence

- `src/elspeth/plugins/hookspecs.py:53-70` defines `elspeth_get_gates` hookspec.
- `docs/contracts/plugin-protocol.md:34-43` declares gates as config-driven system operations, not plugins.
- `src/elspeth/plugins/discovery.py:163-173` excludes gates from plugin discovery.
- `src/elspeth/plugins/manager.py:62-73` excludes gates from builtin registration.

## Impact

- User-facing impact: Misleads developers into thinking gate plugins are supported; any gate plugin implementation will never be discovered or executed.
- Data integrity / security impact: Potentially missing expected routing logic if someone tries to use a gate plugin, leading to silent misconfiguration.
- Performance or cost impact: Low; primarily a correctness/contract issue.

## Root Cause Hypothesis

- Leftover hookspec from pre-refactor gate plugin architecture that was not removed during the gate-to-config migration.

## Proposed Fix

- Code changes (modules/files): Remove `elspeth_get_gates` from `src/elspeth/plugins/hookspecs.py`, and remove related gate hook references in `src/elspeth/plugins/manager.py` and `tests/plugins/test_hookspecs.py`.
- Config or schema changes: None.
- Tests to add/update: Update hookspec tests to stop asserting the gate hook exists; optionally add a negative assertion that only source/transform/sink hooks are present.
- Risks or migration steps: If any out-of-tree code still provides gate plugins, it will break; document the removal as a breaking change consistent with the no-legacy policy.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/contracts/plugin-protocol.md:34-43`
- Observed divergence: Hookspecs still advertise a gate plugin hook even though gates are defined as system operations, not plugins.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Remove the gate hook and related plugin manager/test references, or explicitly reintroduce gate plugins end-to-end (but this contradicts the current protocol).

## Acceptance Criteria

- `elspeth_get_gates` is absent from hookspecs.
- Plugin discovery/manager no longer reference gate hooks.
- Tests pass with updated expectations.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_hookspecs.py`
- New tests required: no, update existing hookspec test expectations.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md`, `docs/plans/completed/plugin-refactor/cleanup-list.md`
