# ADR 003 – Remove Legacy Code

## Status

Accepted (historical).

## Context

Legacy helpers in `src/elspeth/core/legacy/` duplicated the new pipeline implementation,
causing drift and increasing maintenance cost.

## Decision

Delete legacy orchestration helpers after verifying feature parity with the new pipeline.

## Consequences

- Simplified code structure (no duplicate orchestrator logic).
- Tests reference only the new pipeline.
- Any future regression requires reintroducing helpers explicitly via git history if needed.
