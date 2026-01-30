# Bug Report: Deprecated compute_upstream_topology_hash violates no-legacy policy

## Summary

- `compute_upstream_topology_hash` function exists and is documented as "kept for backwards compatibility" which violates CLAUDE.md's No Legacy Code Policy.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/canonical.py:214-224` - function docstring states "kept for backwards compatibility"
- CLAUDE.md:797-834 explicitly forbids backwards compatibility code

## Impact

- User-facing impact: None directly
- Policy: Violates No Legacy Code Policy

## Proposed Fix

- Remove function and update all call sites to use the current API

## Acceptance Criteria

- No backwards compatibility functions remain
- All call sites updated
