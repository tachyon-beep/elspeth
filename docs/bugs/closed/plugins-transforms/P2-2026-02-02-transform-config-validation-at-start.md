# Bug Report: Transforms should validate config before run starts

## Summary

- Transform configs are not consistently validated at run start. Misconfigurations can slip through and only fail when the transform is first executed, causing late failures mid-run.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: user
- Date: 2026-02-02
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2-post-implementation-cleanup
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: any pipeline with misconfigured transform options

## Steps To Reproduce

1. Configure a pipeline with a transform that has invalid options (e.g., wrong field names or missing required option).
2. Start a run.
3. Observe that the run starts and proceeds until the transform is invoked.
4. The run fails at that point due to invalid transform config.

## Expected Behavior

- All transform configs are validated before the run begins.
- If any transform config is invalid, the run fails fast and does not start.

## Actual Behavior

- Validation can be deferred until the transform executes, causing late failure mid-run.

## Impact

- Wasted compute and time due to late failures
- Harder diagnosis (errors appear mid-run rather than at start)
- Inconsistent behavior vs source/sink validation expectations

## Root Cause Hypothesis

- Transform config validation is not consistently invoked during pipeline preflight or run initialization.

## Proposed Fix

- Ensure transform config validation occurs during pipeline construction or run start (before any execution begins).
- Enforce a single preflight validation path for sources, transforms, and sinks.
- Add tests that verify invalid transform configs block run start.

## Acceptance Criteria

- A run with an invalid transform config fails before any execution begins.
- Error message points to the transform and invalid option.

## Tests

- Suggested tests to run: `pytest tests/engine/test_orchestrator.py -k validate -v`
- New tests required: yes (preflight transform validation)

## Notes / Links

- Related issues/PRs: N/A
- Related docs: CLAUDE.md trust model (validation at boundaries)
