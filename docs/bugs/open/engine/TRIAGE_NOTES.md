# Engine Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | best-effort timeout does not resolve coalesces when zero branches arrived | coalesce_executor.py | P1 | P2 | Downgraded |
| 2 | Coalesce ordering invariant not rechecked after gate jump | processor.py | P1 | P2 | Downgraded |
| 3 | Fork branch tokens routed to sink by gate not marked as lost for coalesce | processor.py | P1 | P1 | Confirmed |
| 4 | DAGNavigator create_continuation_work_item misroutes coalesce tokens to branch | dag_navigator.py | P1 | P1 | Confirmed |
| 5 | Duplicate notify_branch_lost silently accepted and overwrites | coalesce_executor.py | P2 | P3 | Downgraded |
| 6 | Gate executor can leave open node states on dispatch errors | executors/gate.py | P1 | P1 | Confirmed |
| 7 | RetryManager misclassifies non-retryable RetryError as MaxRetriesExceeded | retry.py | P1 | -- | Closed (false positive) |
| 8 | SharedBatchAdapter.emit silently drops results when state_id is None | batch_adapter.py | P1 | P2 | Downgraded |
| 9 | ExpressionParser.is_boolean_expression misclassifies bool() calls | expression_parser.py | P1 | P2 | Downgraded |
| 10 | TokenManager.coalesce_tokens does not validate parent token invariants | tokens.py | P1 | P3 | Downgraded |
| 11 | MockClock allows nonfinite or nonmonotonic time | clock.py | P1 | P3 | Downgraded |
| 12 | Stale public usage example in engine __init__.py | __init__.py | P2 | P2 | Confirmed |
| 13 | TriggerEvaluator restore_from_checkpoint accepts impossible empty batch | triggers.py | P2 | -- | Closed (false positive) |

**Result:** 4 confirmed (3 P1, 1 P2), 7 downgraded, 2 closed as false positives.

## Detailed Assessments

### Bug 1: best-effort timeout with zero arrivals (P1 -> P2)

The gap is real -- `check_timeouts()` skips pending entries with empty `arrived` dicts. However, `flush_pending` at end-of-source catches these orphaned entries for all batch runs. Only truly never-ending streaming sources are affected, and the fix is a one-liner else clause in the timeout check. Downgraded because the blast radius is narrow and the mitigation is structural.

### Bug 2: Coalesce ordering invariant not rechecked after gate jump (P1 -> P2)

The invariant gap exists: a gate `next_node_id` jump can place a fork-branch token past its coalesce node without re-validating ordering. However, this requires a very unusual DAG topology -- a gate within a fork branch whose route target is past the coalesce node. DAG validation and structural constraints make this configuration unlikely in practice. The fix (re-check after `next_node_id` assignment) is straightforward.

### Bug 3: Fork branch tokens routed to sink not marked lost (P1 confirmed)

Genuine P1. When a gate routes a forked token to a sink, the token is marked ROUTED but no `notify_branch_lost` is issued to the coalesce node. Sibling branches that do arrive will wait indefinitely (or until timeout) for the routed branch. This is a real correctness gap in the coalesce lifecycle -- every early-exit path must issue a loss notification for forked tokens.

### Bug 4: DAGNavigator continuation misroutes coalesce tokens (P1 confirmed)

Genuine P1. `create_continuation_work_item` conflates "start at branch entry" with "continue from current position." When a coalesced token needs to continue past the merge point, it is incorrectly routed to the branch entry instead of the node after coalesce. This produces incorrect traversal paths and can cause re-execution of branch transforms on the merged token.

### Bug 5: Duplicate notify_branch_lost silently accepted (P2 -> P3)

The overwrite behavior is technically wrong (second loss reason replaces first), but duplicate loss notifications are unreachable through normal code paths. Each token exits through exactly one early-exit path in `_process_single_token`, so a branch cannot be lost twice. This is a defense-in-depth hardening measure, not a production risk.

### Bug 6: Gate executor leaves open node states on dispatch errors (P1 confirmed)

Genuine P1. If `_dispatch_outcome` raises after `begin_node_state`, the node state is left open without completion. This leaks state in the Landscape and can affect resume behavior. The fix requires a try/finally or equivalent cleanup pattern in the gate executor.

### Bug 7: RetryManager misclassifies RetryError (CLOSED -- false positive)

False positive. The analysis assumed that `operation()` could raise `tenacity.RetryError` and that this would be caught by the outer handler. In reality, tenacity with `reraise=False` re-raises non-retryable exceptions directly without wrapping them in `RetryError`. No plugin in the codebase raises `tenacity.RetryError` directly. The claimed misclassification path is unreachable through any known code path.

### Bug 8: SharedBatchAdapter.emit drops results on state_id=None (P1 -> P2)

The silent drop is a real defensive programming violation -- it should crash, not discard. However, `state_id=None` requires a pre-existing executor bug: in all known production paths, `state_id` is always set by `begin_node_state()` before the batch adapter is invoked. The precondition failure this guards against is structurally prevented by the executor lifecycle. Still worth fixing for principle, but not an active production risk.

### Bug 9: ExpressionParser bool() misclassification (P1 -> P2)

The gap in the static boolean classifier is real -- `bool(row['x'])` is not recognized as boolean. However, this does not cause data corruption or audit integrity issues. Users have straightforward workarounds (`row['x'] != 0` instead of `bool(row['x'])`). The impact is validation inconsistency between config-time and runtime, not silent data loss.

### Bug 10: TokenManager coalesce_tokens missing parent validation (P1 -> P3)

The missing validation is technically correct, but the caller structurally prevents the invalid state. The `_pending` dict in `CoalesceExecutor` uses `(coalesce_name, row_id)` as its key, which guarantees all parents in a single coalesce group share the same `row_id`. Additionally, `_execute_merge` is only called when `len(arrived) > 0`, preventing the empty-parents case. Adding the check would be pure defense-in-depth.

### Bug 11: MockClock allows nonfinite/nonmonotonic time (P1 -> P3)

`MockClock` is test-only infrastructure, never instantiated in production. `SystemClock` delegates to `time.monotonic()` which is guaranteed monotonic and finite by the Python runtime. Adding validation to MockClock is a minor test hardening improvement that would prevent hypothetical bad test setups, but has zero production risk.

### Bug 12: Stale usage example in engine __init__.py (P2 confirmed)

Documentation accuracy issue. The public usage example references a removed API pattern. No runtime impact, but misleading for developers reading the module docstring.

### Bug 13: TriggerEvaluator restore_from_checkpoint empty batch (CLOSED -- false positive)

False positive. The analysis claimed that `batch_count=0` could reach `restore_from_checkpoint()`, but `get_checkpoint_state()` explicitly excludes empty buffers with `if not tokens: continue`. The serialization side already guards against the condition the restore side would need to reject. The claimed failure path is unreachable.

## Cross-Cutting Observations

### 1. Bugs 3 and 4 interact -- gate routing + continuation misrouting compound in fork branches

Bugs 3 and 4 both affect fork-branch token handling and can compound. Bug 3 causes missing coalesce loss notifications when a gate routes a branch token to a sink. Bug 4 causes misrouted continuation after coalesce. In a DAG where both conditions occur, a fork branch could be routed to a sink (Bug 3, no loss notification), while the coalesced token from remaining branches is then misrouted back to a branch entry (Bug 4). These should be fixed together as they share the fork/coalesce lifecycle boundary.

### 2. `create_continuation_work_item` conflates branch entry with current position

The root cause of Bug 4 is a conceptual conflation in `DAGNavigator.create_continuation_work_item`. The method does not distinguish between "start processing at the entry of a branch" and "continue processing from the current position in the DAG." For coalesced tokens that need to proceed past the merge node, the method incorrectly uses branch-entry logic instead of continuation-from-node logic. This is a design-level issue, not just a missing conditional.

### 3. Every early-exit path in `_process_single_token` needs coalesce notification for forked tokens

Bug 3 reveals a consistency pattern: any code path that terminates a forked token early (routing to sink, quarantine, failure) must issue a `notify_branch_lost` call to the owning coalesce node. Currently this is handled for some exit paths but not all. A systematic audit of all early-exit paths in `_process_single_token` would identify any additional gaps beyond the sink-routing case identified in Bug 3.

### 4. Static analysis false positive pattern: examining exception handling without understanding library runtime behavior

Bugs 7 and 13 share a common false-positive pattern. The static analysis tool examined exception handling code paths and identified theoretically reachable bad states, but did not account for the runtime behavior of the libraries involved (tenacity's `reraise=False` semantics for Bug 7, `get_checkpoint_state()`'s empty-buffer exclusion for Bug 13). This pattern suggests that future static analysis sweeps should cross-reference library documentation and caller-side guards before escalating exception-path findings to P1.

### 5. Serialization-side guards close restore-side concerns

Bug 13 specifically demonstrates that validation at the serialization boundary can make restore-side validation unnecessary. `get_checkpoint_state()` excludes empty buffers before they are serialized, so `restore_from_checkpoint()` can never receive `batch_count=0` from a legitimately serialized checkpoint. This pattern -- validating at write time to simplify read-time assumptions -- is used elsewhere in the codebase (e.g., canonical JSON normalization before persistence). When evaluating restore-side bugs, always check whether the serialization side already prevents the claimed invalid input.
