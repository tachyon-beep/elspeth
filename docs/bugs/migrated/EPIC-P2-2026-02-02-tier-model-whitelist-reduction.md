## Summary

Reduce the 547-entry tier model whitelist by fixing bug-hiding patterns. Target: <300 entries.

## Severity

- Severity: moderate
- Priority: P2
- Type: epic
- Status: open
- Bead ID: elspeth-rapid-6c2

## Current Progress (2026-02-02)

- **Whitelist: 547 → 362 entries (-185, 34% reduction)**
- **Phase 1.1 COMPLETE** (engine/executors.py): -19 entries
- **Phase 1.2 COMPLETE** (engine/orchestrator.py): -12 entries (Counter refactor)
- **Phase 2 COMPLETE** (per-file rules): -154 entries
- All 787 engine tests pass, 3 commits merged to RC2.1

## What Was Fixed

### Phase 1.1 (executors.py)
1. AggregationExecutor methods now validate node_id against aggregation_settings
2. Checkpoint restore uses direct `[]` for required v1.1 format fields
3. Trigger evaluator access uses direct `[]` after validation
4. `_reset_batch_state` uses direct `[]` with type assertion

### Phase 2 (per-file rules)
- Implemented per-file whitelisting in `enforce_tier_model.py`
- Added PerFileRule dataclass with glob pattern matching
- Added 6 per-file rules for external trust boundaries
- Removed 154 individual entries now covered by file rules

## Key Methodology

The "None = not important" pathology:
- `.get()` returning None conflates "invalid input" with "valid state, no data"
- Fix: Add validation FIRST, then use `.get()` only for legitimate cases

## Next Steps

1. Phase 3: Make AST/type work permanent (expires: null)
2. Review remaining 362 entries for further reduction opportunities

## Key Files

- `config/cicd/enforce_tier_model/` — The whitelist directory
- `src/elspeth/engine/executors/` — Phase 1.1 complete
- `docs/plans/in-progress/2026-02-02-whitelist-reduction.md` — Full plan

## Blocked By

- `w2q7` — ELSPETH-NEXT (P3 epic)
