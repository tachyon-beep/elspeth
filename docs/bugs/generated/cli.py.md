# Bug Report: Resume ignores payload_store.backend and always uses FilesystemPayloadStore

## Summary

- `elspeth resume` instantiates `FilesystemPayloadStore` without validating `payload_store.backend`, so non-filesystem backends are ignored and resume may read the wrong storage or fail unexpectedly.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: settings.yaml with `payload_store.backend` set to a non-filesystem value (e.g., `s3`) and a resumable run

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Set `payload_store.backend` in settings to a non-filesystem value (e.g., `s3`) and ensure `payload_store.base_path` points to a local directory.
2. Run `elspeth resume <run_id> --settings settings.yaml --execute` for a resumable run.

## Expected Behavior

- Resume should fail fast with a clear error stating that only the `filesystem` backend is supported (matching `run` behavior).

## Actual Behavior

- Resume proceeds to create a `FilesystemPayloadStore` and uses `payload_store.base_path` regardless of backend, potentially reading the wrong storage or failing later.

## Evidence

- `src/elspeth/cli.py:1675-1684` — `resume()` always instantiates `FilesystemPayloadStore` after only checking `base_path.exists()`, with no backend validation.
- `src/elspeth/cli.py:815-821` — `run()` explicitly validates `payload_store.backend == "filesystem"` and errors otherwise (resume lacks the same guard).

## Impact

- User-facing impact: Confusing resume failures or silent use of the wrong payload location when backend is not filesystem.
- Data integrity / security impact: Potential to resume against incorrect payloads if local directory exists, leading to incorrect outputs.
- Performance or cost impact: Minimal, but can waste time debugging failed resumes.

## Root Cause Hypothesis

- Resume path omits the backend validation enforced in run/purge, so it always assumes filesystem storage.

## Proposed Fix

- Code changes (modules/files):
  - Add a backend validation guard in `resume()` before `FilesystemPayloadStore` instantiation, mirroring the `run()` check in `src/elspeth/cli.py`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a CLI test in `tests/cli/test_cli.py` to assert resume fails with a clear error when `payload_store.backend != "filesystem"`.
- Risks or migration steps:
  - None; this only tightens validation to match existing behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Resume ignores backend validation that is enforced elsewhere in the CLI.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce the same filesystem-only guard in resume.

## Acceptance Criteria

- `elspeth resume` exits with an explicit error if `payload_store.backend` is not `filesystem`.
- Resume continues to work unchanged for filesystem-backed payloads.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/cli/test_cli.py -k resume`
- New tests required: yes, resume backend validation case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
---
# Bug Report: RateLimitRegistry not closed when resume fails

## Summary

- `_execute_resume_with_instances()` closes `RateLimitRegistry` only on successful resume; if `orchestrator.resume()` raises, rate limiters are never closed.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any resume scenario that triggers an exception inside `orchestrator.resume()`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a resumable run, then force `orchestrator.resume()` to raise (e.g., corrupted payload, DB error, invalid resume graph).
2. Run `elspeth resume <run_id> --execute`.

## Expected Behavior

- `RateLimitRegistry.close()` should always be called, even when resume fails, to release SQLite connections and limiter resources.

## Actual Behavior

- `RateLimitRegistry.close()` is called only after `orchestrator.resume()` returns successfully; on exceptions, the registry is left open.

## Evidence

- `src/elspeth/cli.py:1459-1485` — `rate_limit_registry.close()` is called after `orchestrator.resume()` without a `try/finally` guard.

## Impact

- User-facing impact: Minimal (process often exits), but can cause noisy resource leaks in tests or long-lived processes invoking CLI programmatically.
- Data integrity / security impact: None known.
- Performance or cost impact: Possible file locks and lingering threads for rate limiting persistence.

## Root Cause Hypothesis

- Missing `try/finally` around `orchestrator.resume()` in `_execute_resume_with_instances()`.

## Proposed Fix

- Code changes (modules/files):
  - Wrap `orchestrator.resume()` in `try/finally` and always close `rate_limit_registry`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit or CLI test that forces `orchestrator.resume()` to raise and asserts `RateLimitRegistry.close()` is invoked (monkeypatch a sentinel).
- Risks or migration steps:
  - None; strictly improves cleanup.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Resource cleanup isn’t guaranteed on error paths.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce cleanup via `try/finally`.

## Acceptance Criteria

- `RateLimitRegistry.close()` is executed on both successful and failed resume attempts.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/cli/test_cli.py -k resume`
- New tests required: yes, failure-path cleanup coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
---
# Bug Report: DB connection not closed on early failure in _execute_pipeline_with_instances

## Summary

- `_execute_pipeline_with_instances()` opens `LandscapeDB` before the `try/finally`; if payload store setup fails (unsupported backend or filesystem init error), the DB connection is never closed.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: settings.yaml with `payload_store.backend` not equal to `filesystem` or invalid `payload_store.base_path`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Set `payload_store.backend` to a non-filesystem value in settings.
2. Run `elspeth run --settings settings.yaml --execute`.

## Expected Behavior

- Database connection should be closed even when payload store validation fails.

## Actual Behavior

- `LandscapeDB` is opened before entering the `try/finally`, so early exits skip `db.close()`.

## Evidence

- `src/elspeth/cli.py:807-822` — DB is opened and payload store validation occurs before the `try` block begins; failure paths raise before cleanup.

## Impact

- User-facing impact: Minimal; typically masked by process exit.
- Data integrity / security impact: None known.
- Performance or cost impact: Potential file handle/connection leaks in tests or programmatic invocations.

## Root Cause Hypothesis

- Cleanup scope starts after payload store validation, so exceptions before the `try` bypass `db.close()`.

## Proposed Fix

- Code changes (modules/files):
  - Move DB creation and payload store validation inside the `try` block, or add a broader `try/finally` to cover these steps.
- Config or schema changes: None.
- Tests to add/update:
  - Add a CLI test ensuring no open DB handles when `payload_store.backend` is unsupported (e.g., via monkeypatching `LandscapeDB.from_url` and verifying `close()`).
- Risks or migration steps:
  - None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Resource cleanup is not guaranteed on early error paths.
- Reason (if known): Unknown
- Alignment plan or decision needed: Ensure cleanup spans all error paths.

## Acceptance Criteria

- `LandscapeDB.close()` is called on any early exit from `_execute_pipeline_with_instances()`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/cli/test_cli.py -k run`
- New tests required: yes, early-failure cleanup coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
