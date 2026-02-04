# Bug Report: Bytes Canonicalization Collides With User Dicts Using `__bytes__`

## Summary

- Bytes are normalized to a dict with `{"__bytes__": "<b64>"}`, which is indistinguishable from user data that already contains the same dict shape, producing identical canonical JSON and hashes.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 7a155997ad574d2a10fa3838dd0079b0d67574ff (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory values `b"abc"` and `{"__bytes__": "YWJj"}`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/canonical.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `canonical_json(b"abc")`.
2. Call `canonical_json({"__bytes__": "YWJj"})`.
3. Compare results of `stable_hash` for both inputs.

## Expected Behavior

- Different canonical JSON and hashes for distinct input types, or a hard error when user data uses reserved markers that would collide.

## Actual Behavior

- `canonical_json(b"abc")` and `canonical_json({"__bytes__": "YWJj"})` produce identical canonical JSON and identical `stable_hash` values.

## Evidence

- Bytes are normalized into a dict wrapper at `src/elspeth/core/canonical.py:108-110`, and hashing is based on canonical JSON at `src/elspeth/core/canonical.py:140-173`.
- Reproduction (observed): `canonical_json(b"abc") == canonical_json({"__bytes__":"YWJj"}) == '{"__bytes__":"YWJj"}'` and `stable_hash(b"abc") == stable_hash({"__bytes__":"YWJj"})`.

## Impact

- User-facing impact: Audit trail cannot distinguish a raw bytes payload from a dict that happens to use the `__bytes__` key, creating ambiguous lineage.
- Data integrity / security impact: Non-cryptographic collision in canonicalization undermines “traceable to source data” guarantees; different inputs can map to the same audit hash.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `_normalize_value` encodes bytes into a plain dict with a common key name and there is no reserved-key enforcement or disambiguation, making the canonical representation non-injective for bytes vs user dicts.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/core/canonical.py`, introduce a reserved-marker strategy that is enforced. Options include wrapping bytes in a dedicated internal wrapper type and emitting a tagged JSON object while rejecting any user dicts that contain the reserved marker (raise `ValueError`), ensuring no ambiguous shapes are accepted.
- Config or schema changes: None.
- Tests to add/update: Add a unit test in `tests/core/test_canonical.py` that asserts either (a) bytes and `{"__bytes__": "..."}`
  produce different canonical JSON/hashes, or (b) user dicts containing the reserved marker raise `ValueError`.
- Risks or migration steps: This is a breaking change for data that already uses the reserved marker key; enforce the reservation explicitly and document it.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L15-L19` (audit trail must be traceable; no inference).
- Observed divergence: Canonicalization is not injective for bytes vs dicts using the same wrapper key, allowing ambiguous audit hashes.
- Reason (if known): Convenience encoding without reserved-key enforcement.
- Alignment plan or decision needed: Reserve and enforce marker keys (or use a distinct tagging strategy) to guarantee unambiguous canonicalization.

## Acceptance Criteria

- `stable_hash(b"abc")` differs from `stable_hash({"__bytes__":"YWJj"})`, or `canonical_json({"__bytes__":"YWJj"})` raises a `ValueError` due to reserved-key collision.
- New unit test covers the collision case and passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_canonical.py`
- New tests required: yes, add a collision-resistance test for bytes vs dict marker.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
