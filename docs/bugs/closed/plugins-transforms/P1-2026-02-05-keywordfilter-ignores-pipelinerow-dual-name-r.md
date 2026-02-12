# Bug Report: KeywordFilter Ignores PipelineRow Dual-Name Resolution, Allowing Original-Name Fields to Bypass Filtering

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Resolved**
- Resolution summary:
  - Updated `KeywordFilter` field lookup to use `PipelineRow` access semantics (`in row` + `row[field]`) instead of plain-dict membership/value checks.
  - Added regression coverage for original header-name resolution (`"Amount USD"` resolving to `amount_usd`) so blocked content is no longer bypassed.
  - Fix landed in commit `81796824` on branch `RC3-quality-sprint`.


## Summary

- KeywordFilter converts `PipelineRow` to a plain dict and checks field membership on normalized keys only, so configurations that reference original header names (e.g., `"Amount USD"`) silently skip scanning and allow blocked content through.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (branch `RC2.3-pipeline-row`)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: PipelineRow with SchemaContract that maps original headers to normalized names

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/transforms/keyword_filter.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `SchemaContract` with an original name mapping such as original `"Amount USD"` → normalized `amount_usd`, and a `PipelineRow` with data `{"amount_usd": "secret"}`.
2. Configure `KeywordFilter` with `fields: ["Amount USD"]`, `blocked_patterns: ["secret"]`, and a valid schema/on_error.
3. Call `KeywordFilter.process(row, ctx)`.

## Expected Behavior

- The filter should resolve the original field name via `PipelineRow.__getitem__` and return `TransformResult.error(...)` with `reason="blocked_content"`.

## Actual Behavior

- The filter uses `row.to_dict()` and checks membership in the normalized dict, so `"Amount USD"` is not found and the row passes through as success.

## Evidence

- `src/elspeth/plugins/transforms/keyword_filter.py:109-116` converts to `row_dict` and skips fields not present in the dict, bypassing dual-name resolution.
- `src/elspeth/contracts/schema_contract.py:518-536` documents that `PipelineRow.__getitem__` resolves both original and normalized field names.
- `docs/plans/completed/2026-02-03-pipelinerow-migration.md:874-889` specifies transforms should access fields via `PipelineRow` to use dual-name resolution.

## Impact

- User-facing impact: Content that should be blocked by regex can pass through if configs use original headers, undermining the filter’s purpose.
- Data integrity / security impact: Sensitive data can reach downstream transforms/sinks and be recorded as unblocked, breaking audit expectations for filtering.
- Performance or cost impact: None directly.

## Root Cause Hypothesis

- The transform converts `PipelineRow` to a dict and performs membership/value checks on the normalized keys, losing the contract-based dual-name resolution.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/plugins/transforms/keyword_filter.py` to access values via `row[field_name]` with a `try/except KeyError` (or similar) so original names resolve correctly; only use `row.to_dict()` for output serialization.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/unit/plugins/transforms/test_keyword_filter.py` that uses a `PipelineRow` with original-name mappings and ensures original-name fields are detected and blocked.
- Risks or migration steps: Low; behavior should remain unchanged for normalized names, with added support for original names.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-02-03-pipelinerow-migration.md:874-889`.
- Observed divergence: KeywordFilter checks fields on a plain dict instead of using `PipelineRow` dual-name access.
- Reason (if known): Incomplete PipelineRow migration in the transform’s field access path.
- Alignment plan or decision needed: Use `PipelineRow` access for field lookup, preserving dual-name behavior.

## Acceptance Criteria

- KeywordFilter blocks content when `fields` uses original header names, and existing behavior for normalized names remains unchanged.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_keyword_filter.py -v`
- New tests required: yes, add coverage for original-name field resolution.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-03-pipelinerow-migration.md`

---

## Verification (2026-02-12)

- Reproduced before fix:
  - Configuring `fields: ["Amount USD"]` with data under normalized key `amount_usd` returned `success` and did not block matched patterns.
- Post-fix behavior:
  - `KeywordFilter` correctly resolves configured original header names via `PipelineRow` and returns `TransformResult.error` with `reason="blocked_content"`.
  - Existing normalized-name behavior remains unchanged.
- Tests executed:
  - `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_keyword_filter.py -q`
  - `.venv/bin/python -m pytest tests/unit/contracts/transform_contracts/test_keyword_filter_contract.py -q`
  - `.venv/bin/python -m ruff check src/elspeth/plugins/transforms/keyword_filter.py tests/unit/plugins/transforms/test_keyword_filter.py`
