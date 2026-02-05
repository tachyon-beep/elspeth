# Bug Report: Batch-Aware Transform Contract Mismatch (BaseTransform.process Signature)

## Summary

- BaseTransform defines `process(row: PipelineRow, ctx)` even though batch-aware transforms are executed with `list[dict]`, forcing type ignores and enabling incorrect implementations to pass review until runtime.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a new `BaseTransform` subclass with `is_batch_aware = True` and `process(self, row: PipelineRow, ctx)` that calls `row.to_dict()`.
2. Configure it as an aggregation transform and run a pipeline until a batch flush triggers.
3. The engine passes `list[dict]` to `process`, raising `AttributeError` or otherwise misbehaving.

## Expected Behavior

- The base contract and typing should accept the batch input shape (`list[dict]`) when `is_batch_aware=True`, or the engine should only pass `PipelineRow` to `process` to match the contract.

## Actual Behavior

- The engine passes `list[dict]` for batch-aware transforms, while `BaseTransform.process` is typed as `PipelineRow`, leading to runtime errors for new implementations and forcing `# type: ignore[override]` in existing batch transforms.

## Evidence

- `src/elspeth/plugins/base.py:45-101` declares batch-aware behavior in docstring but `process` signature accepts `PipelineRow` only.
- `src/elspeth/engine/executors.py:1290-1302` calls `transform.process(buffered_rows, ctx)` where `buffered_rows` is `list[dict]`.
- `src/elspeth/plugins/transforms/batch_stats.py:99-101` uses `# type: ignore[override]` to bypass the signature mismatch.

## Impact

- User-facing impact: Aggregation pipelines can crash at flush time if a batch-aware transform follows the base signature literally.
- Data integrity / security impact: Batch failures stop output emission; audit trail records failure but results are missing.
- Performance or cost impact: N/A

## Root Cause Hypothesis

- The base contract in `BaseTransform` (and related protocol typing) was not updated to reflect the batch input shape after the aggregation refactor, causing a persistent mismatch between contract and runtime behavior.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/plugins/base.py` `BaseTransform.process` to accept a batch-aware input shape (e.g., `PipelineRow | list[dict[str, Any]]`) and align documentation; update `src/elspeth/plugins/protocols.py` to match; update batch-aware transforms to match the new signature and remove `# type: ignore[override]`.
- Config or schema changes: None.
- Tests to add/update: Add a type-check or unit test asserting batch-aware transform signatures; exercise `tests/engine/test_processor_batch.py` with a transform that validates input shape.
- Risks or migration steps: Requires touching all batch-aware transforms to align signatures; run mypy/ruff to catch remaining mismatches.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/protocols.py:146-157` (batch-aware transforms receive `list[dict]`).
- Observed divergence: BaseTransform’s signature only accepts `PipelineRow`, contradicting the protocol’s batch mode description and engine behavior.
- Reason (if known): Likely incomplete alignment during the pipeline-row/aggregation refactor.
- Alignment plan or decision needed: Align BaseTransform and protocol signatures with engine batch semantics and remove type ignores.

## Acceptance Criteria

- Batch-aware transforms no longer require `# type: ignore[override]`.
- `BaseTransform.process` and `TransformProtocol` signatures match the actual runtime input for batch mode.
- Mypy passes with batch-aware transforms typed correctly.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_processor_batch.py`, `.venv/bin/python -m mypy src/`
- New tests required: yes, add a signature/shape contract check for batch-aware transforms.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
---
# Bug Report: BaseGate Uses Defensive `.get` for `fork_to`, Masking Config Bugs

## Summary

- `BaseGate.__init__` uses `config.get("fork_to")` for system-owned config, violating the “no defensive programming” rule and potentially masking missing `fork_to` when it is required for fork routes.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate a `BaseGate` subclass with a config dict that omits `fork_to`, even though routes include `fork`.
2. Gate initializes successfully because `.get` returns `None`.
3. Gate later attempts to fork, leading to misrouting or a delayed failure rather than an immediate config crash.

## Expected Behavior

- Initialization should crash immediately if `fork_to` is missing in validated config, because this is system-owned data and should never be silently defaulted.

## Actual Behavior

- `.get("fork_to")` returns `None`, allowing gate initialization to proceed even when `fork_to` is required.

## Evidence

- `src/elspeth/plugins/base.py:176-180` uses `config.get("fork_to")` despite comment stating no defensive checks are needed.
- `CLAUDE.md:918-921` prohibits `.get()` for system-owned data (must crash on internal bugs).
- `src/elspeth/core/config.py:314-320` defines `fork_to` as a validated field; `src/elspeth/core/config.py:386-392` requires `fork_to` when routes include `fork`.

## Impact

- User-facing impact: Gates can proceed with missing fork configuration, leading to incorrect routing or delayed failures.
- Data integrity / security impact: Misrouting creates incorrect audit outcomes and violates “crash on our data” principle.
- Performance or cost impact: N/A

## Root Cause Hypothesis

- Defensive access pattern was retained in `BaseGate.__init__`, contradicting the “no defensive programming” policy and allowing missing config fields to slip through.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/base.py`, replace `config.get("fork_to")` with direct access `config["fork_to"]` to crash on missing keys.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that instantiating a gate with missing `fork_to` raises immediately when routes include `fork`.
- Risks or migration steps: If any code path constructs gate configs without `fork_to` (even when `None`), update those constructors to include the key.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918-921` (no defensive `.get()` for system-owned data).
- Observed divergence: BaseGate uses `.get()` to avoid missing key errors.
- Reason (if known): Likely leftover convenience pattern from earlier configs.
- Alignment plan or decision needed: Enforce direct access to config fields in base classes.

## Acceptance Criteria

- `BaseGate.__init__` crashes on missing `fork_to` instead of defaulting to `None`.
- No defensive `.get()` usage remains in base gate config handling.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_processor_batch.py` (if gate tests live elsewhere, target those), `.venv/bin/python -m ruff check src/`
- New tests required: yes, add a gate config validation/instantiation failure test for missing `fork_to`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (defensive programming prohibition)
