# Bug Report: Lookup Data Mutability Produces Stale `lookup_hash` (Audit Mismatch)

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `PromptTemplate` stores `lookup_data` by reference and computes `lookup_hash` only once; if the lookup dict is mutated after initialization, the rendered prompt uses new values while the audit hash remains tied to the old data.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b4
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory dict lookup data

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/templates.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a lookup dict: `lookup = {"k": "v1"}`
2. Initialize `PromptTemplate` with `template_string="Value: {{ lookup.k }}"` and `lookup_data=lookup`
3. Mutate the lookup dict after initialization: `lookup["k"] = "v2"`
4. Call `render_with_metadata({})`
5. Compare `rendered.prompt` (will show `v2`) to `rendered.lookup_hash` (hash still computed from `{"k": "v1"}`)

## Expected Behavior

- `lookup_hash` should always match the lookup data actually used to render the prompt (either by freezing the lookup data at init or recomputing the hash if the data changes).

## Actual Behavior

- `lookup_hash` is computed once at initialization and does not reflect later mutations of `lookup_data`, causing audit metadata to diverge from the rendered prompt.

## Evidence

- `src/elspeth/plugins/llm/templates.py:103-108` stores `lookup_data` by reference and computes `lookup_hash` once.
- `src/elspeth/plugins/llm/templates.py:167-171` passes mutable `_lookup_data` directly into the Jinja context.
- `src/elspeth/plugins/llm/templates.py:203-210` computes `variables_hash` after rendering, so any in-render mutation would further desync hashes.

## Impact

- User-facing impact: Prompt audit fields can claim a lookup hash that does not correspond to the data actually used in the prompt.
- Data integrity / security impact: Audit trail integrity is weakened; hashes no longer reliably verify inputs used for decisions.
- Performance or cost impact: None directly; potential rework during audits.

## Root Cause Hypothesis

- `lookup_data` is not copied or frozen on ingestion, and `lookup_hash` is computed only once from the initial mutable dict.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/llm/templates.py` — deep copy and freeze `lookup_data` (e.g., `MappingProxyType`) before storing; compute `lookup_hash` from the frozen copy; consider hashing row data before render and/or pass immutable row context when no contract is provided.
- Config or schema changes: None
- Tests to add/update: Add unit test asserting that mutating the original `lookup_data` after template construction does not change rendered content without corresponding hash change; add test that `lookup_hash` matches canonical JSON of the stored lookup.
- Risks or migration steps: If any templates relied on mutating `lookup` at render time, this will break; that behavior should be considered invalid for auditability.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L15-L19` (audit trail must be traceable and hash integrity must be verifiable)
- Observed divergence: Hashes can become detached from the actual lookup data used in prompt rendering.
- Reason (if known): Lookup data stored by reference and not frozen.
- Alignment plan or decision needed: Freeze/copy lookup data at init and ensure audit hash reflects the immutable version used for rendering.

## Acceptance Criteria

- `lookup_hash` always matches the canonical JSON of the lookup data used during rendering.
- Mutating the original lookup dict after `PromptTemplate` initialization does not affect rendering or is explicitly prevented.
- (Optional) Row data hashes are computed from immutable inputs to prevent in-render mutation from corrupting audit metadata.

## Tests

- Suggested tests to run: `pytest tests/plugins/llm/ -k template`
- New tests required: yes, unit test covering lookup mutation and hash consistency

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md#L15-L19`
