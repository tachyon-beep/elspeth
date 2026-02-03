# Bug Report: RetryPolicy `max_attempts` floats are silently truncated

## Summary

- `RuntimeRetryConfig.from_policy()` accepts float values for `max_attempts` and truncates them via `int()`, violating the `RetryPolicy` contract (`max_attempts: int`) and silently altering retry behavior.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (config-only)

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `RetryPolicy` dict with `max_attempts=2.9` (float).
2. Call `RuntimeRetryConfig.from_policy(policy)`.
3. Observe `config.max_attempts == 2` with no error.

## Expected Behavior

- Non-integer floats for `max_attempts` should be rejected (ValueError) to honor the `RetryPolicy` contract (`max_attempts: int`), or at minimum require integer-valued floats (e.g., `3.0`).

## Actual Behavior

- Float values are coerced with `int()` and truncated, silently changing the configured retry attempts.

## Evidence

- `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py:69-76` (`_validate_int_field` converts floats via `int(value)`).
- `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py:214-252` (`from_policy` uses `_validate_int_field` for `max_attempts`).
- `/home/john/elspeth-rapid/src/elspeth/contracts/engine.py:33-46` (`RetryPolicy.max_attempts` is declared as `int`).

## Impact

- User-facing impact: Retry count can be lower than intended, causing avoidable failures.
- Data integrity / security impact: Config intent is misrepresented; auditability suffers because effective behavior differs from config input.
- Performance or cost impact: Fewer retries can reduce cost but increase failure rate; behavior becomes unpredictable relative to config.

## Root Cause Hypothesis

- `_validate_int_field` treats float values as valid and truncates them, which violates the `RetryPolicy` type contract and hides misconfiguration.

## Proposed Fix

- Code changes (modules/files): In `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py`, change `_validate_int_field` to reject non-integer floats (e.g., `value.is_integer()` check) and raise `ValueError` for fractional floats.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/contracts/config/test_runtime_retry.py` that `max_attempts=2.5` raises `ValueError`, and optionally that `max_attempts=3.0` is accepted or rejected per decision.
- Risks or migration steps: Tightening validation may break configs that currently pass floats; document the requirement for integer `max_attempts`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/src/elspeth/contracts/engine.py:33-46` (`RetryPolicy` defines `max_attempts: int`).
- Observed divergence: Runtime validation accepts floats and truncates them instead of enforcing integer-only.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce integer-only values for `max_attempts` at the policy boundary.

## Acceptance Criteria

- `RuntimeRetryConfig.from_policy({"max_attempts": 2.5})` raises a clear `ValueError`.
- `RuntimeRetryConfig.from_policy({"max_attempts": 3})` still succeeds.
- Unit tests cover fractional-float rejection (and integer-valued float handling if allowed).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/config/test_runtime_retry.py -v`
- New tests required: yes, add explicit fractional-float rejection test for `max_attempts`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `/home/john/elspeth-rapid/src/elspeth/contracts/engine.py`
---
# Bug Report: RuntimeRateLimitConfig immutability violated by mutable `services` dict

## Summary

- `RuntimeRateLimitConfig` is declared frozen/immutable but contains a mutable `services` dict, enabling runtime mutation of configuration state.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (config-only)

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Build a runtime config via `RuntimeRateLimitConfig.from_settings(RateLimitSettings())`.
2. Mutate `config.services["openai"] = ServiceRateLimit(requests_per_minute=100)`.
3. Observe mutation succeeds despite the config being “frozen”.

## Expected Behavior

- Runtime config should be immutable; mutation of `services` should raise `TypeError` or be impossible.

## Actual Behavior

- `services` is a mutable dict, so it can be changed mid-execution.

## Evidence

- `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py:7-10` (design principle: “Frozen (immutable) - runtime config should never change mid-execution”).
- `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py:285-288` (`services: dict[str, "ServiceRateLimit"]`).
- `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py:317-345` (default uses `{}` and `from_settings` uses `dict(...)`, both mutable).

## Impact

- User-facing impact: Rate-limiting behavior can change mid-run without any audit trail or explicit config reload.
- Data integrity / security impact: Mutable runtime config undermines the immutability guarantee for auditability.
- Performance or cost impact: Inconsistent rate limits could cause bursts or throttling inconsistencies.

## Root Cause Hypothesis

- The `services` field uses a mutable dict, and dataclass `frozen=True` does not deep-freeze nested structures.

## Proposed Fix

- Code changes (modules/files): In `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py`, change `services` to an immutable mapping (e.g., `Mapping[str, ServiceRateLimit]`) and wrap with `types.MappingProxyType` in `default()` and `from_settings()`.
- Config or schema changes: None.
- Tests to add/update: Add a test that mutating `services` raises `TypeError`.
- Risks or migration steps: None, unless external code relies on mutating `services` (which should be considered a bug).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py:7-10`
- Observed divergence: Config declares immutability but contains a mutable dict.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce immutability of nested config structures.

## Acceptance Criteria

- `services` is immutable at runtime (mutation raises `TypeError`).
- `RuntimeRateLimitConfig.get_service_config()` still works with the immutable mapping.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/config/test_runtime_rate_limit.py -v`
- New tests required: yes, add an immutability test for `services`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py`
