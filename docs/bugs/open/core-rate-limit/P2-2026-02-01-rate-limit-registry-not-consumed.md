# Bug Report: RateLimitRegistry is never consumed by plugins (limits not enforced)

## Summary

- The CLI creates a `RateLimitRegistry` and the Orchestrator passes it into `PluginContext`, but no plugin/client acquires a limiter. As a result, configured rate limits are a no-op and requests are not throttled.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-01
- Related run/issue ID: N/A

## Environment

- Commit/branch: local workspace (uncommitted)
- OS: Linux
- Python version: Python 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Investigate RC2 known limitation around rate limiting.
- Model/version: GPT-5 (Codex CLI)
- Tooling and permissions (sandbox/approvals): workspace-write, no escalations
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: Code inspection only

## Steps To Reproduce

1. Configure `rate_limit` in settings (enable, set very low requests_per_minute for a service).
2. Run a pipeline that performs multiple external calls (LLM or HTTP).
3. Observe that calls proceed without throttling.

## Expected Behavior

- External calls should acquire a limiter from `RateLimitRegistry`, enforcing configured request rates.

## Actual Behavior

- No limiter acquisition occurs anywhere in plugins/clients/transforms; configured rate limits are never enforced.

## Evidence

- CLI instantiates registry and passes it to Orchestrator: `src/elspeth/cli.py` (rate_limit_registry setup).
- Orchestrator passes registry into `PluginContext`: `src/elspeth/engine/orchestrator.py` (context construction).
- `PluginContext` defines `rate_limit_registry`, but no usage in plugins/clients: `src/elspeth/plugins/context.py`.
- Search results show **no** `rate_limit_registry` usage in `src/elspeth/plugins/` (only in CLI/orchestrator).

## Impact

- User-facing impact: Rate limit configuration has no effect; pipelines can exceed provider limits and trigger 429/5xx errors.
- Data integrity / security impact: None directly.
- Performance or cost impact: Unbounded request rates can spike cost and cause widespread retries.

## Root Cause Hypothesis

- The registry is created and passed through, but no code consumes it (missing `get_limiter(...).acquire()` calls).

## Proposed Fix

- Code changes (modules/files):
  - Add limiter acquisition in `AuditedHTTPClient` and `AuditedLLMClient` (or at the call sites in LLM/HTTP transforms).
  - Decide on service naming convention for `get_limiter(service_name)`.
- Config or schema changes: None.
- Tests to add/update:
  - Integration test that configures a low rate limit and asserts elapsed time or limiter call count.
  - Unit test that verifies audited clients call the limiter when present.
- Risks or migration steps:
  - Ensure limiter acquisition is optional and no-op when disabled.

## Architectural Deviations

- Spec or doc reference: `docs/release/rc2-checklist.md` (Known limitation: rate limiting not wired)
- Observed divergence: Registry is instantiated but never used.
- Reason (if known): Missing integration at client boundary.
- Alignment plan or decision needed: Decide whether limits should live in audited clients or in transforms.

## Acceptance Criteria

- With rate limiting enabled, external calls are throttled according to settings.
- With rate limiting disabled, behavior remains unchanged.
- Tests demonstrate throttling behavior.

## Tests

- Suggested tests to run: `pytest tests/integration/test_llm_transforms.py -k rate_limit`
- New tests required: Yes.

## Notes / Links

- Related docs: `docs/release/rc2-checklist.md`, `docs/plans/in-progress/RC2-remediation.md` (CRIT-01)
