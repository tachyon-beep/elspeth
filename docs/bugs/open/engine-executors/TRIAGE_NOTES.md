# Engine Executors Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/engine-executors/` (4 findings from static analysis)
**Source code reviewed:** `aggregation.py`, `sink.py`, `transform.py`, `gate.py`

## Summary

| # | Bug | Original | Triaged | Verdict |
|---|-----|----------|---------|---------|
| 1 | AggregationExecutor flush non-terminal states | P1 | **P1 confirmed** | Real — PluginContractViolation from hash escapes with OPEN node state + EXECUTING batch |
| 2 | SinkExecutor begin_node_state failure orphans | P1 | **P2 downgrade** | Real but Tier 1 DB crash is intended; compensating writes would also fail |
| 3 | TransformExecutor terminality violation | P1 | **P1 confirmed** | First claim real (same pattern as #1); second claim (ordering) is correct behavior |
| 4 | ctx.token only set for batch-mixin | P2 | **P2 confirmed** | Real telemetry gap; one-line fix |

## Detailed Assessment

### 1. AggregationExecutor flush non-terminal — CONFIRMED P1

`execute_flush()` wraps only `transform.process()` in try/except (lines 360-422). Post-process hash
computation at line 431/433 can raise `PluginContractViolation` which propagates with the node_state
still OPEN and the batch in EXECUTING status. Neither reaches a terminal state.

### 2. SinkExecutor begin_node_state failure — DOWNGRADED to P2

The state-opening loop at lines 148-160 has no try/except. If `begin_node_state()` fails after
successful inserts, those states are orphaned. However, `begin_node_state()` is a Tier 1 DB
operation — crashes indicate catastrophic database issues (disk full, connection lost), and
compensating `complete_node_state(FAILED)` calls would also fail against the same broken database.

### 3. TransformExecutor terminality — CONFIRMED P1 (first claim only)

**Claim 1 (PluginContractViolation before terminal state):** Confirmed. Same pattern as Bug 1 —
`stable_hash()` at line 297-302 sits outside the try/except, so PluginContractViolation leaves
node_state OPEN.

**Claim 2 (update_node_output_contract after COMPLETED):** This is actually correct behavior.
`complete_node_state(COMPLETED)` at line 323 runs before `update_node_output_contract()` at line
335-351. If the metadata write fails, the terminal state is already durably recorded — this is
the safer ordering.

### 4. ctx.token only for batch-mixin — CONFIRMED P2

`ctx.token` is set at line 226 only for `BatchTransformMixin` instances. Regular transforms get
`ctx.token = None`. WebScrapeTransform handles None gracefully but loses telemetry token_id.
Fix: add `ctx.token = token` to the else branch at line 250.

## Cross-Cutting Observations

1. **Bugs 1 and 3 share identical root cause:** post-process `stable_hash` raising
   `PluginContractViolation` outside the try/except guard. A single refactor pattern (outer
   guard ensuring terminal state before re-raise) would fix both.

2. **Related to engine bug:** Gate executor open-node-states bug (in engine/ folder) is the
   same class of issue — `OrchestrationInvariantError` escaping without node state completion.
   All three executor types share this pattern.
