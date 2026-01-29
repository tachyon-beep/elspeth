# Bug Report: CallVerifier lacks field-level order sensitivity configuration

## Summary

- `CallVerifier` only supports instance-level `ignore_order` configuration. Users cannot specify that some fields are order-sensitive (ranked results) while others are order-insensitive (tags) within the same verification session. This forces a global trade-off between false negatives (missing drift) and false positives (noisy alerts).

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: claude-review-board
- Date: 2026-01-29
- Related run/issue ID: P3-2026-01-21-verifier-ignore-order-hides-drift (Phase 2)

## Environment

- Commit/branch: `fix/P2-aggregation-metadata-hardcoded`
- OS: Linux 6.8.0-90-generic
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: 4-perspective review of P3-2026-01-21 fix proposal
- Model/version: Claude Opus 4.5
- Tooling and permissions: workspace-write
- Determinism details: N/A
- Notable tool calls or steps: axiom-system-architect, axiom-python-engineering, ordis-quality-engineering, yzmir-systems-thinking reviews

## Steps To Reproduce

1. Configure a verification session with mixed field semantics:
   - `ranked_results`: order matters (semantic)
   - `tags`: order doesn't matter (set-like)
2. Attempt to set different `ignore_order` behavior for each field
3. Observe that only global `ignore_order` is available

## Expected Behavior

- Field-level configuration allowing per-field order sensitivity:
  ```python
  verifier = CallVerifier(
      recorder,
      source_run_id="run-123",
      field_order_config={
          "root['ranked_results']": False,  # Order matters
          "root['tags']": True,             # Order doesn't matter
      },
      default_ignore_order=False,
  )
  ```

## Actual Behavior

- Only global `ignore_order` parameter available
- Must choose between catching ranked-list drift (false positives on tags) or ignoring tag order (false negatives on ranked lists)

## Evidence

- Current implementation: `src/elspeth/plugins/clients/verifier.py:120-137`
- DeepDiff supports `ignore_order_func` for per-element control, currently unused

## Impact

- User-facing impact: suboptimal trade-off between false positives and false negatives
- Data integrity / security impact: audit verification less precise than it could be
- Performance or cost impact: N/A

## Root Cause Hypothesis

- Initial implementation used simplest DeepDiff configuration
- Field-level semantics require additional metadata infrastructure

## Proposed Fix

- Code changes (modules/files):
  - Add `field_order_config: dict[str, bool] | None` parameter to `CallVerifier.__init__()`
  - Implement custom `ignore_order_func` callback that checks path against config
  - Default behavior: use global `ignore_order` for unconfigured paths
- Config or schema changes:
  - Consider YAML schema for verifier field configuration
- Tests to add/update:
  - Test field-level override with mixed semantics
  - Test default fallback behavior
  - Test nested field paths
- Risks or migration steps:
  - Additive change, no breaking impact
  - May want to expose in CLI/config files later

## Architectural Deviations

- Spec or doc reference: N/A
- Observed divergence: global-only configuration
- Reason (if known): MVP implementation
- Alignment plan or decision needed: define field metadata schema for verifier

## Acceptance Criteria

- Users can configure per-field `ignore_order` behavior
- Unconfigured fields fall back to global default
- Documentation explains field-level configuration

## Tests

- Suggested tests to run: `pytest tests/plugins/clients/test_verifier.py -k field_order`
- New tests required: yes

## Notes / Links

- Related issues/PRs: P3-2026-01-21-verifier-ignore-order-hides-drift (Phase 1 adds global config)
- Related design docs: N/A
- Systems Thinking Analysis: "Fixes That Fail" archetype identified - field-level config is the proper leverage point

## Review Board Analysis (2026-01-29)

This ticket was created as Phase 2 of a two-phase approach recommended by the 4-perspective review board:

**Phase 1 (P3-2026-01-21):** Add `ignore_order` parameter with default `True` (non-breaking)
**Phase 2 (This ticket):** Add field-level configuration (proper leverage point)

The review identified that changing the global default to `False` without field-level config would trigger a "Fixes That Fail" dynamic - initial success catching ranked-list drift, followed by trust collapse from false positives on unordered fields.

### Key Quotes from Review

**Architecture:** *"If a user needs mixed semantics, they can create two CallVerifier instances."* - This is a workaround, not a solution.

**Systems Thinking:** *"Some fields are order-sensitive (ranked_results), some are order-insensitive (tags). Same type, different semantics → global default CANNOT be correct for both."*

### Implementation Priority

This should be implemented BEFORE changing the default to `ignore_order=False`. The proper sequence:

1. Phase 1: Add configurable `ignore_order` (keep default `True`)
2. Phase 2: Add field-level config (this ticket)
3. Phase 3: Change default to `False` with migration tooling
