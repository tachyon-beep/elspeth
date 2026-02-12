# Bug Report: Template Field Extraction Misidentifies `row.get()` and Drops Actual Field

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `extract_jinja2_fields("{{ row.get('status') }}")` still returns `frozenset({'get'})`.
  - The extractor still records `row.get` as an attribute and does not parse `Call` args to capture `'status'`.
- Current evidence:
  - `src/elspeth/core/templates.py:99`
  - `src/elspeth/core/templates.py:103`
  - `src/elspeth/core/templates.py:143`

## Summary

- `extract_jinja2_fields*` treats `row.get(...)` as a field named `get` and ignores the actual key argument, so templates using `row.get('field')` produce incorrect required field lists.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e (RC2.3-pipeline-row)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/templates.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `extract_jinja2_fields("{{ row.get('status') }}")`.
2. Observe the returned field set.

## Expected Behavior

- The extractor should include `status` (or the string literal passed to `row.get`) and should not treat `get` as a field.

## Actual Behavior

- The extractor returns `frozenset({'get'})`, missing `status`.

## Evidence

- `src/elspeth/core/templates.py:99` adds `node.attr` for any `Getattr` on the namespace, so `row.get` is treated as a field.
- `src/elspeth/core/templates.py:103` only handles `Getitem` and never inspects `Call` nodes, so `row.get('field')` arguments are ignored.
- `tests/plugins/llm/test_contract_aware_template.py:159` shows Jinja2 templates using `row.get('nonexistent', 'N/A')` are valid and expected.
- Local reproduction: `extract_jinja2_fields("{{ row.get('status') }}")` returns `frozenset({'get'})`.

## Impact

- User-facing impact: Developers following guidance will generate incorrect `required_input_fields` for templates that use `row.get`, leading to missing dependency declarations.
- Data integrity / security impact: Missing declared inputs can allow configurations that later fail at render time (e.g., UndefinedError) or mask required fields.
- Performance or cost impact: Minimal direct impact; indirect reruns due to misconfigured templates.

## Root Cause Hypothesis

- The AST walk only recognizes `Getattr` and `Getitem` on the namespace; it does not handle `Call` nodes for `row.get(...)`, and it incorrectly treats `row.get` as a field name.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/templates.py` add explicit handling for `Call` nodes where the callee is `row.get` and the first arg is a string constant; skip recording `"get"` as a field in this case.
- Config or schema changes: N/A
- Tests to add/update: Add unit tests in `tests/core/test_templates.py` for `row.get('field')` and `row.get('field', default)` to ensure extracted fields include the key and exclude `"get"`.
- Risks or migration steps: Low risk; ensure property tests still pass and details extractor behavior is consistent.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-02-02-phase4-template-resolver.md:553`
- Observed divergence: Template field discovery does not recognize `row.get(...)` even though templates use it.
- Reason (if known): Missing AST handling for `Call` nodes.
- Alignment plan or decision needed: Implement `row.get` call parsing and add tests.

## Acceptance Criteria

- `extract_jinja2_fields("{{ row.get('status') }}")` returns `frozenset({'status'})` and `extract_jinja2_fields_with_details` includes `status` without a spurious `get` entry.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_templates.py`
- New tests required: yes, add cases for `row.get('field')` and `row.get('field', default)`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-02-phase4-template-resolver.md:553`

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `4ff1d29f`
- Fix summary: Fix Jinja field extraction for row.get keys
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.

