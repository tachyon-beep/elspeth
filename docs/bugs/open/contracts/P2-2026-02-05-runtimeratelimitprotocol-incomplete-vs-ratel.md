# Bug Report: RuntimeRateLimitProtocol Incomplete vs. RateLimitRegistry Usage

## Summary

- `RuntimeRateLimitProtocol` omits `persistence_path` and `get_service_config`, but `RateLimitRegistry` relies on both, so the protocol does not actually describe the minimal interface the registry requires.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/contracts/config/protocols.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Define a config object that only implements `enabled` and `default_requests_per_minute` (i.e., satisfies `RuntimeRateLimitProtocol` as currently defined).
2. Pass that object to `RateLimitRegistry(...)` and call `get_limiter("openai")`.
3. Observe `AttributeError` because `get_service_config` or `persistence_path` is missing.

## Expected Behavior

- The protocol should include all attributes/methods `RateLimitRegistry` actually uses so structural typing prevents incomplete configs.

## Actual Behavior

- The protocol excludes `persistence_path` and `get_service_config`, so a config can satisfy the protocol but still fail at runtime in `RateLimitRegistry`.

## Evidence

- `RuntimeRateLimitProtocol` only requires `enabled` and `default_requests_per_minute` and explicitly says other fields are “handled separately.” `src/elspeth/contracts/config/protocols.py:81-100`
- `RateLimitRegistry` uses `config.get_service_config(...)` and `config.persistence_path` when creating limiters. `src/elspeth/core/rate_limit/registry.py:95-105`

## Impact

- User-facing impact: Potential runtime crash if a config object is constructed to satisfy the protocol but lacks `get_service_config` or `persistence_path`.
- Data integrity / security impact: N/A
- Performance or cost impact: N/A

## Root Cause Hypothesis

- The protocol definition drifted from the actual `RateLimitRegistry` usage, leaving required fields/methods out of the contract.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/config/protocols.py`: Add `persistence_path: str | None` and `get_service_config(service_name: str)` to `RuntimeRateLimitProtocol`, and update the docstring to reflect actual usage.
- Config or schema changes: None.
- Tests to add/update:
  - Add a small unit test that `RuntimeRateLimitConfig` satisfies `RuntimeRateLimitProtocol` and that the protocol includes `get_service_config` and `persistence_path` (or a structural typing/mypy check if available).
- Risks or migration steps:
  - Low risk; updates protocol to match existing runtime behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/config/protocols.py:9-13`
- Observed divergence: Protocol claims to define the minimal interface components need, but `RuntimeRateLimitProtocol` omits fields/methods used by `RateLimitRegistry`.
- Reason (if known): Likely an oversight during config refactor.
- Alignment plan or decision needed: Update the protocol to include `persistence_path` and `get_service_config` (or remove the “RateLimitRegistry expects” claim if intentionally minimal).

## Acceptance Criteria

- `RuntimeRateLimitProtocol` includes all attributes/methods used by `RateLimitRegistry`.
- A config object satisfying the protocol can be used by `RateLimitRegistry` without runtime attribute errors.
- Protocol docstring matches actual component requirements.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_config_alignment.py`
- New tests required: yes, add a protocol compliance test for rate limit config.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/config/protocols.py`
