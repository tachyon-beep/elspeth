# Bug Report: Aggregation Batch-Aware Check Masks Contract Violations

## Summary

- `instantiate_plugins_from_config()` uses `getattr(..., False)` for `is_batch_aware`, which hides missing required attributes on system-owned transforms and violates the defensive programming prohibition.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 3aa2fa93d8ebd2650c7f3de23b318b60498cd81c (branch `RC2.3-pipeline-row`)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/cli_helpers.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Register a transform that does not expose `is_batch_aware` (e.g., mistakenly not inheriting `BaseTransform`) and reference it in an `aggregations` config.
2. Run `elspeth validate` or `elspeth run` to instantiate plugins.
3. Observe the error message indicating `is_batch_aware=False` rather than a protocol/attribute failure.

## Expected Behavior

- Direct access to `transform.is_batch_aware` should surface an `AttributeError` (or explicit protocol violation) if the attribute is missing.

## Actual Behavior

- `getattr(transform, "is_batch_aware", False)` treats a missing attribute as `False` and raises a misleading configuration error.

## Evidence

- Defensive `getattr` in aggregation check: `src/elspeth/cli_helpers.py:54`
- `is_batch_aware` is a required attribute on transforms: `src/elspeth/plugins/protocols.py:142-195`
- `BaseTransform` defines `is_batch_aware` for all system transforms: `src/elspeth/plugins/base.py:71-74`
- Defensive attribute access is explicitly запрещен: `CLAUDE.md:918-920`

## Impact

- User-facing impact: Misleading error messages when a transform violates the protocol, making debugging harder.
- Data integrity / security impact: Low; this is a bug-hiding pattern that weakens contract enforcement.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Use of defensive `getattr(..., False)` on system-owned plugin attributes, which masks contract violations instead of surfacing them.

## Proposed Fix

- Code changes (modules/files): Replace `getattr(transform, "is_batch_aware", False)` with direct `transform.is_batch_aware` access and retain the ValueError only for explicit `False` values in `src/elspeth/cli_helpers.py`.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that registers a transform missing `is_batch_aware` and asserts that instantiation fails with an attribute/protocol error rather than a misleading ValueError.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918-920`
- Observed divergence: Defensive `getattr` used on system-owned transform attributes.
- Reason (if known): Likely intended to guard against missing attributes, but this violates the “no defensive programming” rule.
- Alignment plan or decision needed: Use direct attribute access to surface contract violations and maintain policy compliance.

## Acceptance Criteria

- Aggregation instantiation uses direct `transform.is_batch_aware` access.
- Missing `is_batch_aware` raises a protocol/attribute error rather than “is_batch_aware=False”.
- Non-batch-aware transforms still yield the current ValueError with an accurate message.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k cli_helpers`
- New tests required: yes, add a unit test that exercises missing `is_batch_aware` on aggregation instantiation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (defensive programming prohibition)
