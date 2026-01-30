# Bug Report: PluginContext.record_call bypasses centralized call_index allocation

## Summary

- PluginContext.record_call allocates call_index locally instead of using LandscapeRecorder.allocate_call_index, which can produce duplicate (state_id, call_index) values when a transform mixes ctx.record_call with audited clients in the same node state.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline where a transform uses both ctx.record_call and an Audited*Client within the same state_id

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for /home/john/elspeth-rapid/src/elspeth/plugins/context.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a transform that uses ctx.llm_client (AuditedLLMClient) for one external call and ctx.record_call for another call in the same process() invocation (same state_id).
2. Run a pipeline so both calls occur within a single node state.
3. Observe call recording in Landscape.

## Expected Behavior

- call_index values are unique and sequential for a given state_id across all call sources, with no IntegrityError.

## Actual Behavior

- call_index from ctx.record_call starts at 0 independently of LandscapeRecorder.allocate_call_index; audited clients also allocate from 0, causing duplicate (state_id, call_index) and an IntegrityError or a failed call record.

## Evidence

- PluginContext.record_call uses a local counter and does not consult the recorder allocator: `src/elspeth/plugins/context.py:215-259`.
- LandscapeRecorder explicitly defines allocate_call_index as the single source of truth for cross-client uniqueness: `src/elspeth/core/landscape/recorder.py:1782-1819`.
- The calls table enforces a UNIQUE constraint on (state_id, call_index): `src/elspeth/core/landscape/schema.py:210-226`.

## Impact

- User-facing impact: Pipeline runs can fail with IntegrityError when mixed call recording paths are used.
- Data integrity / security impact: External call audit trail becomes incomplete or inconsistent for affected states.
- Performance or cost impact: Failed runs may trigger retries or manual remediation.

## Root Cause Hypothesis

- PluginContext.record_call increments its own _call_index instead of delegating to LandscapeRecorder.allocate_call_index, so mixed call paths do not coordinate index allocation.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/context.py` to use `self.landscape.allocate_call_index(self.state_id)` for call_index generation.
  - Remove or deprecate `_call_index` / `_call_index_lock` if no longer needed, or keep but unused.
- Config or schema changes: Unknown
- Tests to add/update:
  - Add a test that mixes ctx.record_call with an AuditedHTTPClient/AuditedLLMClient in the same state_id and asserts unique call_index values.
- Risks or migration steps:
  - Ensure any existing reliance on ctx._call_index ordering is preserved by the recorder allocator (it should be).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/landscape/recorder.py:1782-1819`
- Observed divergence: PluginContext.record_call bypasses the documented single-source-of-truth allocator for call_index.
- Reason (if known): Unknown
- Alignment plan or decision needed: Align PluginContext.record_call with LandscapeRecorder.allocate_call_index to guarantee uniqueness across call sources.

## Acceptance Criteria

- ctx.record_call delegates call_index allocation to LandscapeRecorder.
- Mixed usage of ctx.record_call and audited clients no longer produces duplicate call_index values.
- New test covering mixed call sources passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_gate_executor.py tests/plugins/clients/test_audited_http_client.py`
- New tests required: yes, add a mixed call_index allocation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/core/landscape/recorder.py`
