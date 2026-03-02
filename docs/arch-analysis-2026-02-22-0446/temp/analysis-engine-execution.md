# Engine Execution Layer: Architecture Analysis

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6
**Scope:** engine/executors/ (6 files), engine infrastructure (8 files)

---

## Per-File Analysis

### 1. `engine/executors/transform.py` (488 lines)

**Purpose:** Wraps `transform.process()` with full audit recording, timing, error routing, and contract evolution. Handles both synchronous transforms and asynchronous batch transforms (via `BatchTransformMixin`).

**Key classes/functions:**
- `TransformExecutor` -- singleton-per-pipeline executor that processes individual transform operations
  - `execute_transform()` -- main entry point; handles a SINGLE ATTEMPT (retry is caller's responsibility)
  - `_get_batch_adapter()` -- lazily creates `SharedBatchAdapter` per mixin-based transform

**Dependencies:**
- `contracts`: TokenInfo, ExecutionError, NodeStateStatus, RoutingMode, PluginContext, NodeID, StepResolver
- `core.canonical`: stable_hash
- `core.landscape`: LandscapeRecorder
- `engine.executors.state_guard`: NodeStateGuard
- `engine.spans`: SpanFactory
- `plugins.batching.mixin`: BatchTransformMixin
- `plugins.protocols`: TransformProtocol
- `plugins.results`: TransformResult
- `plugins.transforms.field_collision`: detect_field_collisions (lazy import)
- `contracts.contract_propagation`: propagate_contract (lazy import)

**Error handling model:**
- Plugin exceptions propagate (plugins are system code -- bugs crash)
- `TransformResult.error()` is a legitimate processing failure, routed via `on_error` config
- `NodeStateGuard` guarantees terminal state even if post-processing raises
- TimeoutError on batch transforms triggers eviction of stale buffer entry

**Concerns:**
1. **MINOR -- `getattr` for `_on_start_called` (line 204):** Uses `getattr(transform, "_on_start_called", True)` with a True default for non-BaseTransform implementations. This is explicitly noted as a lifecycle guard and the default-True means it only activates for BaseTransform subclasses where the attribute exists but is False. Documented and intentional, but it is a private-attribute access pattern that could break if the attribute is renamed.
2. **MINOR -- Lazy imports inside hot path (lines 217, 237, 386):** `detect_field_collisions`, `ValidationError`, and `propagate_contract` are imported inside `execute_transform()`. These are conditional imports (only triggered when declared_output_fields or validate_input is set), which is acceptable for performance, but the import-inside-function pattern is unconventional.
3. **SOUND -- Error routing architecture:** The error routing path is well-structured. The `error_edge_ids` map is pre-built by the processor from the edge map, the DIVERT routing event is recorded co-located with the node_state lifecycle, and the "discard" case is handled cleanly.

---

### 2. `engine/executors/gate.py` (410 lines)

**Purpose:** Wraps config-driven gate evaluation with audit recording and routing. Gates are expression-based (no gate plugins), evaluating conditions via `ExpressionParser` and routing tokens to sinks, processing nodes, forks, or continue.

**Key classes/functions:**
- `_RouteDispatchOutcome` -- internal dataclass for routing dispatch results
- `GateExecutor` -- executes config-driven gates
  - `execute_config_gate()` -- evaluates condition, looks up route, dispatches
  - `_dispatch_resolved_destination()` -- handles CONTINUE/FORK/SINK/PROCESSING_NODE destinations
  - `_resolve_route_destination()` -- maps route label to concrete destination (fail-closed)
  - `_record_routing()` -- records routing events for audit trail

**Dependencies:**
- `contracts`: ConfigGateReason, ExecutionError, RouteDestination, RouteDestinationKind, RoutingAction, RoutingReason, RoutingSpec, TokenInfo, RoutingMode
- `contracts.node_state_context`: GateEvaluationContext
- `core.config`: GateSettings
- `core.canonical`: stable_hash
- `core.landscape`: LandscapeRecorder
- `engine.executors.types`: GateOutcome, MissingEdgeError
- `engine.expression_parser`: ExpressionParser
- `engine.spans`: SpanFactory
- `engine.tokens`: TokenManager (TYPE_CHECKING only)

**Error handling model:**
- Expression evaluation failures are caught, recorded in node_state as FAILED, then re-raised
- Route label not found in routes config is caught, recorded, then ValueError raised
- Routing dispatch failures (MissingEdgeError, OrchestrationInvariantError) are caught, recorded, then re-raised
- Pattern: every failure path records the node_state as FAILED before raising

**Concerns:**
1. **MINOR -- No NodeStateGuard in gate executor (lines 223-263):** Unlike TransformExecutor and AggregationExecutor, GateExecutor uses manual begin/complete pairs for node states rather than NodeStateGuard. The gate has three explicit try/except blocks that each call `complete_node_state(FAILED)` before re-raising. This is functionally correct but is the exact pattern NodeStateGuard was designed to replace. If any future code is added between begin and complete without a try/except, it could leave states OPEN. **Recommend refactoring to use NodeStateGuard for consistency.**
2. **SOUND -- Route resolution architecture:** The two-level resolution (label -> RouteDestination -> dispatch) is clean and supports all destination types uniformly.

---

### 3. `engine/executors/sink.py` (387 lines)

**Purpose:** Wraps `sink.write()` and `sink.flush()` with artifact recording, token outcome recording, and node state management. Creates a node_state for EACH token to prove terminal state in the audit trail.

**Key classes/functions:**
- `SinkExecutor` -- executes sink writes with artifact recording
  - `write()` -- main entry point; creates per-token node states, validates input, writes, flushes, records outcomes
  - `_complete_states_failed()` -- helper to fail all opened sink states (used in 5 error paths)

**Dependencies:**
- `contracts`: Artifact, ExecutionError, NodeStateOpen, PendingOutcome, TokenInfo
- `contracts.plugin_context`: PluginContext
- `core.landscape`: LandscapeRecorder
- `core.operations`: track_operation
- `engine.spans`: SpanFactory
- `plugins.protocols`: SinkProtocol

**Error handling model:**
- Six distinct failure paths, all calling `_complete_states_failed()` before re-raising:
  1. begin_node_state fails mid-batch
  2. Contract merge fails
  3. Pre-write validation fails
  4. sink.write() fails
  5. sink.flush() fails
  6. Checkpoint callback fails (logged, NOT raised -- sink write is durable)
- Durability ordering: write -> flush -> complete states -> register artifact -> record outcomes -> checkpoint

**Concerns:**
1. **MINOR -- No NodeStateGuard usage:** Like gate.py, sink.py manages node states manually with begin/complete pairs. The complexity is higher here because it manages N states simultaneously (one per token in the batch). NodeStateGuard is designed for single-state management, so the batch pattern may not fit directly. The manual approach is well-structured with the helper method.
2. **SOUND -- Durability ordering:** The write -> flush -> state-complete -> artifact -> outcome ordering is correct. Outcomes are only recorded after durability is confirmed, satisfying Invariant 3.
3. **SOUND -- Checkpoint failure handling (line 373):** Correctly logs and continues rather than raising, since sink writes are durable and cannot be undone. Documents the consequence (resume will replay = duplicate writes).

---

### 4. `engine/executors/aggregation.py` (943 lines)

**Purpose:** Manages the full batch lifecycle: buffering rows, evaluating triggers, executing flush with audit recording, and checkpointing/restoring aggregation state. The largest and most complex executor.

**Key classes/functions:**
- `_AggregationNodeState` -- consolidated per-node state (replaces 7 parallel dicts)
- `AggregationExecutor` -- manages batch lifecycle
  - `buffer_row()` -- buffers a row, creates batch on first row, records batch membership
  - `execute_flush()` -- transitions batch through executing -> completed/failed, handles BatchPendingError
  - `get_checkpoint_state()` / `restore_from_checkpoint()` -- serialization/deserialization
  - `should_flush()` / `get_trigger_type()` / `check_flush_status()` -- trigger evaluation delegation
  - `restore_batch()` / `restore_state()` -- recovery from interrupted runs

**Dependencies:**
- `contracts`: BatchPendingError, ExecutionError, PipelineRow, SchemaContract, TokenInfo
- `contracts.aggregation_checkpoint`: AggregationCheckpointState, AggregationNodeCheckpoint, AggregationTokenCheckpoint
- `contracts.enums`: BatchStatus, NodeStateStatus, TriggerType
- `contracts.node_state_context`: AggregationFlushContext
- `core.config`: AggregationSettings
- `core.canonical`: stable_hash
- `core.landscape`: LandscapeRecorder
- `engine.clock`: Clock, DEFAULT_CLOCK
- `engine.executors.state_guard`: NodeStateGuard
- `engine.spans`: SpanFactory
- `engine.triggers`: TriggerEvaluator
- `plugins.protocols`: BatchTransformProtocol

**Error handling model:**
- `NodeStateGuard` ensures node state terminality during flush
- `BatchPendingError` is a control-flow signal (not an error) -- node_state gets PENDING status
- Batch lifecycle cleanup in outer except: fails batch, resets state, clears buffers
- Special handling for `batch_pending=True`: does NOT wipe in-memory state (external batch exists)
- Checkpoint size validation (10MB limit) with RuntimeError

**Concerns:**
1. **MINOR -- `_AggregationNodeState` is mutable dataclass (line 51):** Uses `@dataclass(slots=True)` without frozen=True because fields are mutated in-place. This is intentional and documented, but the mutability means concurrent access would be unsafe. Single-threaded orchestrator makes this safe in practice.
2. **MINOR -- `get_batch_id()` uses `.get()` (line 803):** Uses `self._nodes.get(node_id)` instead of direct access, documented as "Does not validate against aggregation_settings since this is a testing/inspection method." This is a deviation from the prohibition on defensive patterns, but is documented and justified.
3. **SOUND -- Consolidated state:** The refactoring from 7 parallel dicts to a single `_AggregationNodeState` dataclass is a clear improvement. Eliminates structural divergence bugs where buffers and tokens could get out of sync.
4. **SOUND -- Checkpoint versioning:** Uses explicit version strings with rejection on mismatch. Preserves trigger fire times across resume for "first to fire wins" ordering.

---

### 5. `engine/executors/state_guard.py` (203 lines)

**Purpose:** Context manager that structurally guarantees node states reach terminal status. Encodes the invariant "every token reaches exactly one terminal state" as a structural guarantee rather than relying on manual try/except blocks.

**Key classes/functions:**
- `NodeStateGuard` -- context manager for node state lifecycle
  - `__enter__()` -- opens node state via recorder
  - `__exit__()` -- auto-completes as FAILED if not explicitly completed; raises if clean exit without complete()
  - `complete()` -- explicitly completes the state; marks guard as completed
  - `state_id` / `state` properties -- access to opened state

**Dependencies:**
- `contracts`: ExecutionError, NodeStateOpen, NodeStateStatus
- `contracts.errors`: OrchestrationInvariantError
- `core.landscape`: LandscapeRecorder

**Error handling model:**
- Three exit scenarios:
  1. `complete()` called before exit -- `__exit__` is a no-op (normal path)
  2. Exception with no `complete()` -- auto-complete as FAILED, propagate exception
  3. Clean exit without `complete()` -- record FAILED, then raise OrchestrationInvariantError
- If recording FAILED in __exit__ itself fails (DB down), logs error and does not mask original exception

**Concerns:**
1. **SOUND -- Well-designed pattern.** The three-case handling is correct and comprehensive. The "clean exit without complete" case catches programming errors in the executor.
2. **SOUND -- `__slots__` usage.** Appropriate for a frequently-instantiated context manager.
3. **OBSERVATION:** Only used by TransformExecutor and AggregationExecutor. GateExecutor and SinkExecutor use manual begin/complete patterns.

---

### 6. `engine/executors/types.py` (45 lines)

**Purpose:** Shared types for executor modules. Contains `MissingEdgeError` and `GateOutcome`.

**Key classes/functions:**
- `MissingEdgeError` -- raised when routing refers to an unregistered edge (audit integrity error)
- `GateOutcome` -- result dataclass containing gate result, updated token, child tokens, sink name, next node

**Dependencies:**
- `contracts`: TokenInfo
- `contracts.types`: NodeID
- `plugins.results`: GateResult

**Concerns:** None. Clean, minimal shared type definitions.

---

### 7. `engine/retry.py` (147 lines)

**Purpose:** Configurable retry logic wrapping tenacity. Provides exponential backoff with jitter for transform execution.

**Key classes/functions:**
- `MaxRetriesExceeded` -- raised when max retry attempts exceeded (wraps last error)
- `RetryManager` -- tenacity-based retry with audit integration
  - `execute_with_retry()` -- executes operation with retry, invokes on_retry callback before each sleep

**Dependencies:**
- `tenacity`: Retrying, RetryCallState, RetryError, retry_if_exception, stop_after_attempt, wait_exponential_jitter
- `contracts.config`: RuntimeRetryProtocol

**Error handling model:**
- Uses tenacity's `Retrying` iterator pattern
- `is_retryable` callback determines if exception should trigger retry
- `on_retry` callback fires via `before_sleep` hook (only when retry will actually occur)
- Converts tenacity's 1-based attempt numbering to 0-based for audit convention
- `RetryError` (retries exhausted) -> `MaxRetriesExceeded`
- Non-retryable exceptions propagate immediately

**Concerns:**
1. **SOUND -- Correct RuntimeRetryProtocol usage.** Config accessed via protocol properties: `max_attempts`, `base_delay`, `max_delay`, `exponential_base`, `jitter`. All five protocol fields are used, which aligns with the Settings->Runtime config pattern.
2. **SOUND -- Clean tenacity integration.** Uses the iterator pattern which gives more control than the decorator pattern.
3. **MINOR -- `attempt` tracking (line 103-130):** The `attempt` variable is updated inside the for loop but also used outside after `RetryError`. The `last_error` fallback chain (`last_error or e.last_attempt.exception()`) handles the edge case correctly.

---

### 8. `engine/tokens.py` (407 lines)

**Purpose:** High-level token lifecycle management. Wraps LandscapeRecorder for token operations: create, fork, coalesce, expand, update.

**Key classes/functions:**
- `TokenManager` -- manages token lifecycle
  - `create_initial_token()` -- creates token from source row with contract
  - `create_quarantine_token()` -- creates token for invalid data (minimal OBSERVED contract)
  - `create_token_for_existing_row()` -- resume support (row exists, new token)
  - `fork_token()` -- ATOMIC: creates children + records parent FORKED outcome
  - `coalesce_tokens()` -- merges multiple tokens into one
  - `expand_token()` -- deaggregation: 1 input -> N outputs (ATOMIC)
  - `update_row_data()` -- updates token's row data after transform

**Dependencies:**
- `contracts`: SourceRow, TokenInfo
- `contracts.errors`: OrchestrationInvariantError
- `contracts.schema_contract`: PipelineRow, SchemaContract
- `contracts.types`: NodeID, StepResolver
- `core.landscape`: LandscapeRecorder
- `contracts.payload_store`: PayloadStore (TYPE_CHECKING only)

**Error handling model:**
- Guards on preconditions: contract must exist on source_row, quarantine row must be quarantined, locked contract for expand
- All parents must share row_id for coalesce (validated)
- Uses deepcopy for fork/expand to prevent shared mutable state across branches

**Concerns:**
1. **MINOR -- `payload_store` parameter accepted but never used (line 61):** The `__init__` accepts a `payload_store` parameter, stores it as `self._payload_store`, but it is never referenced in any method. The docstring says "Payload persistence is now handled by LandscapeRecorder.create_row()." This is dead code.
2. **SOUND -- Deepcopy for fork/expand:** Critical for audit integrity. Without deepcopy, mutations in one branch would leak to siblings.
3. **SOUND -- Step resolution via injected StepResolver:** Clean dependency injection pattern. Callers pass NodeID, not step_in_pipeline.

---

### 9. `engine/triggers.py` (306 lines)

**Purpose:** Evaluates trigger conditions for aggregation batches. Supports count, timeout, and condition triggers with "first to fire wins" semantics.

**Key classes/functions:**
- `TriggerEvaluator` -- evaluates triggers with OR logic
  - `record_accept()` -- records row acceptance, tracks when triggers first fire
  - `should_trigger()` -- evaluates all trigger conditions, reports earliest-firing
  - `which_triggered()` / `get_trigger_type()` -- audit trail support
  - `get_age_seconds()` / `get_count_fire_offset()` / `get_condition_fire_offset()` -- checkpoint support
  - `restore_from_checkpoint()` -- restores evaluator state from checkpoint data
  - `reset()` -- resets for new batch

**Dependencies:**
- `contracts.enums`: TriggerType
- `core.config`: TriggerConfig
- `engine.clock`: Clock, DEFAULT_CLOCK
- `engine.expression_parser`: ExpressionParser

**Error handling model:**
- Condition expressions that return non-boolean raise TypeError (defense-in-depth)
- Condition fire time is latched (once fired, always honored) to prevent window-based conditions from "unfiring"

**Concerns:**
1. **SOUND -- Latching semantics:** The condition fire time latching (P1-2026-02-05 fix) correctly prevents window-based conditions like `batch_age_seconds < 0.5` from unfiring after the window closes.
2. **SOUND -- Checkpoint/restore API:** Preserves fire time offsets for ordering correctness across resume.
3. **MINOR -- `should_trigger()` re-evaluates condition (line 175):** When condition hasn't fired yet, it re-evaluates on each call with current time context. This is necessary for time-dependent conditions but means the expression parser runs on every call. Pre-parsed expression mitigates performance impact.

---

### 10. `engine/batch_adapter.py` (273 lines)

**Purpose:** Adapter connecting TransformExecutor's synchronous row-by-row processing with BatchTransformMixin's asynchronous worker pool. Routes results from the release thread back to the correct waiter via (token_id, state_id) keying.

**Key classes/functions:**
- `_WaiterEntry` -- consolidated waiter state (event + result slot)
- `RowWaiter` -- blocks on wait() until result arrives; cleans up on timeout
- `SharedBatchAdapter` -- output port for batch transforms
  - `register()` -- creates waiter before accept() (pre-registers for result delivery)
  - `emit()` -- routes result from worker thread to correct waiter
  - `_signal_waiters_by_token_id()` -- fallback for state_id=None executor bugs

**Dependencies:**
- `contracts`: ExceptionResult
- `contracts.errors`: OrchestrationInvariantError
- `contracts.identity`: TokenInfo (TYPE_CHECKING only)
- `contracts`: TransformResult (TYPE_CHECKING only)

**Error handling model:**
- TimeoutError raised when waiter doesn't receive result within timeout
- ExceptionResult wraps plugin bugs from worker threads, re-raised in waiter.wait()
- state_id=None handling: scans all entries by token_id and delivers error (fail-fast, not hang)
- Stale results (from timed-out attempts) are silently discarded
- First-result-wins: duplicate emits on already-signaled entries are discarded

**Concerns:**
1. **SOUND -- Retry safety via (token_id, state_id) keying:** Elegant solution to prevent stale results from being delivered to retry attempts. Each attempt gets a unique state_id.
2. **SOUND -- Thread safety:** Lock protects all shared state. Register/emit/wait correctly synchronize.
3. **MINOR -- Memory cleanup on timeout (line 109-111):** Timeout path pops the entry. This is correct, but if the worker thread calls emit() concurrently, the entry might already be popped. The emit() method handles this ("If no entry exists... result is discarded").

---

### 11. `engine/coalesce_executor.py` (1083 lines)

**Purpose:** Stateful barrier that holds tokens from parallel fork paths until merge conditions are met. Supports four policies (require_all, first, quorum, best_effort) and three merge strategies (union, nested, select).

**Key classes/functions:**
- `CoalesceOutcome` -- result of coalesce accept operation
- `_BranchEntry` -- frozen per-branch state (token, arrival time, state_id)
- `_PendingCoalesce` -- tracks pending tokens for a single row_id
- `CoalesceExecutor` -- the coalesce barrier
  - `register_coalesce()` -- registers a coalesce point with settings
  - `accept()` -- accepts a token; returns merged if conditions met, held otherwise
  - `check_timeouts()` -- checks for timed-out pending coalesces
  - `flush_pending()` -- end-of-source: resolves all pending coalesces
  - `notify_branch_lost()` -- handles error-routed branches that will never arrive
  - `_execute_merge()` -- performs the actual merge with contract handling
  - `_fail_pending()` -- shared failure recording helper
  - `_mark_completed()` -- bounded FIFO set for late-arrival detection

**Dependencies:**
- `contracts`: TokenInfo, CoalesceMetadata, ArrivalOrderEntry
- `contracts.enums`: NodeStateStatus, RowOutcome
- `contracts.schema_contract`: FieldContract, PipelineRow, SchemaContract
- `core.config`: CoalesceSettings
- `core.landscape`: LandscapeRecorder
- `engine.clock`: Clock, DEFAULT_CLOCK
- `engine.spans`: SpanFactory
- `engine.tokens`: TokenManager (TYPE_CHECKING only)

**Error handling model:**
- Duplicate arrivals raise ValueError (bug in upstream code)
- Late arrivals (after merge completed) get FAILED state + FAILED outcome, gracefully handled
- Branch loss notifications trigger re-evaluation based on policy
- `_completed_keys` uses bounded OrderedDict with FIFO eviction for memory safety
- Contract merge failures raise OrchestrationInvariantError
- select_branch not arrived = explicit failure, not silent fallback

**Concerns:**
1. **MINOR -- No NodeStateGuard:** Like gate.py, uses manual begin/complete pairs. The barrier pattern (hold then complete later) doesn't fit cleanly into NodeStateGuard's "open in __enter__, complete in with-block" model because states are opened in `accept()` and completed later in `_execute_merge()`.
2. **MINOR -- `_last_union_collisions` instance variable as side-channel (line 151):** `_merge_data()` sets `self._last_union_collisions` which is then consumed by `_execute_merge()`. This is a side-channel coupling between two methods. A return-value approach would be cleaner but would require changing the _merge_data signature.
3. **SOUND -- Bounded memory for completed keys:** FIFO eviction with configurable max prevents OOM. Eviction is logged. Trade-off (late arrivals after eviction create new pending entries) is documented and acceptable.
4. **SOUND -- Branch loss handling:** The `notify_branch_lost()` / `_evaluate_after_loss()` pattern is well-designed. Each policy has clear consequences for branch loss.

---

### 12. `engine/expression_parser.py` (657 lines)

**Purpose:** Safe expression parser for gate conditions and trigger conditions. Uses Python's `ast` module with a whitelist-based validator and a separate evaluator. Explicitly NOT eval().

**Key classes/functions:**
- `ExpressionSecurityError` / `ExpressionSyntaxError` / `ExpressionEvaluationError` -- typed exceptions
- `_ExpressionValidator` -- AST visitor that rejects forbidden constructs at parse time
- `_ExpressionEvaluator` -- AST visitor that evaluates validated expressions at runtime
- `ExpressionParser` -- public API: parse+validate at construction, evaluate against row data
  - `is_boolean_expression()` -- static analysis for config validation

**Dependencies:**
- `ast`, `operator` (standard library)
- `types.MappingProxyType` (immutable operator tables)

**Error handling model:**
- Two-phase: parse-time validation (security) + runtime evaluation (operational)
- Fail-closed default: unhandled AST expression nodes are rejected
- Runtime errors (KeyError, ZeroDivisionError, TypeError) wrapped in ExpressionEvaluationError
- Operator tables are MappingProxyType (immutable) to prevent runtime tampering

**Concerns:**
1. **SOUND -- Defense-in-depth:** The fail-closed `visit()` override for unhandled expression types is excellent. Future Python AST additions won't silently pass.
2. **SOUND -- No eval():** The AST approach is correct for config-driven expressions.
3. **MINOR -- `is/is not` restriction (line 220):** Restricts `is`/`is not` to None checks only. This is a good security restriction but the error message could be more helpful about using `==`/`!=` instead.
4. **SOUND -- Immutable operator tables:** MappingProxyType prevents runtime modification of allowed operators.

---

### 13. `engine/clock.py` (123 lines)

**Purpose:** Clock abstraction for testable timeout logic. Provides Protocol-based interface with SystemClock (production) and MockClock (testing).

**Key classes/functions:**
- `Clock` -- Protocol with single `monotonic()` method
- `SystemClock` -- delegates to `time.monotonic()`
- `MockClock` -- controllable clock with `advance()` and `set()` methods
- `DEFAULT_CLOCK` -- module-level SystemClock instance

**Dependencies:**
- `time`, `math` (standard library)

**Error handling model:**
- MockClock validates inputs: NaN/Infinity rejected, negative advance rejected, non-monotonic set rejected
- DEFAULT_CLOCK is a module-level singleton (not frozen, but immutable in practice)

**Concerns:**
1. **SOUND -- Clean abstraction.** Protocol-based, simple, no over-engineering.
2. **SOUND -- MockClock safety.** Input validation prevents non-monotonic time and NaN/Infinity corruption.

---

### 14. `engine/spans.py` (296 lines)

**Purpose:** OpenTelemetry span factory. Creates structured spans for pipeline execution. Falls back to no-op mode when no tracer is configured.

**Key classes/functions:**
- `NoOpSpan` -- no-op span for disabled tracing
- `SpanFactory` -- creates typed spans for run, source, row, transform, gate, aggregation, sink
  - Each span method is a `@contextmanager` returning `Span | NoOpSpan`

**Dependencies:**
- `opentelemetry.trace` (TYPE_CHECKING only)

**Error handling model:**
- Graceful degradation: all methods return NoOpSpan when tracer is None
- Singleton `_NOOP_SPAN` avoids repeated allocations

**Concerns:**
1. **MINOR -- Truthy check for span attributes (line 173):** Uses `if node_id:` instead of `if node_id is not None:`. For strings, this means an empty string `""` would not be set as an attribute. Since node_ids should never be empty strings, this is unlikely to matter in practice, but the CLAUDE.md manifesto prefers `is not None` checks over truthiness.
2. **SOUND -- Consistent span structure.** All spans include plugin.name and plugin.type. node_id, input_hash, and token_ids are consistently offered where relevant.

---

## Overall Architecture Analysis

### 1. Executor Architecture

The four executors (Transform, Gate, Aggregation, Sink) follow a consistent pattern:

```
Input (Token + Context) -> Audit Open -> Execute Plugin -> Audit Close -> Output
```

Each executor:
- Opens a node_state before execution
- Times the operation
- Records audit fields on the result
- Completes the node_state with appropriate status
- Emits OpenTelemetry spans

**Key differences:**
| Executor | Node State Mgmt | Batching | State Complexity |
|----------|----------------|----------|-----------------|
| Transform | NodeStateGuard | Single row (+ batch mixin) | Low |
| Gate | Manual begin/complete | Single row | Low |
| Aggregation | NodeStateGuard | Multi-row batch | High (lifecycle) |
| Sink | Manual begin/complete | Multi-row batch | Medium (N states) |

### 2. State Guard Pattern

NodeStateGuard encodes the invariant "every token reaches terminal state" as a structural guarantee. It is used by TransformExecutor and AggregationExecutor but not by GateExecutor or SinkExecutor.

**Gap:** GateExecutor has three separate try/except blocks that each manually complete the state as FAILED before re-raising. This is exactly the pattern NodeStateGuard was designed to eliminate. SinkExecutor has a more complex pattern (N simultaneous states) that doesn't fit NodeStateGuard's single-state model.

**Recommendation:** Refactor GateExecutor to use NodeStateGuard. The pattern fits directly -- gate execution is a single operation with a single state. For SinkExecutor, the batch pattern is genuinely different and the manual approach with `_complete_states_failed()` is appropriate.

### 3. Retry Architecture

RetryManager correctly uses RuntimeRetryProtocol for structural typing. The tenacity integration is clean:
- Uses iterator pattern (not decorator) for more control
- `before_sleep` hook fires on_retry callback only when retry will actually occur
- Converts 1-based tenacity numbering to 0-based for audit convention
- MaxRetriesExceeded wraps the last error for caller context

The protocol fields used are: `max_attempts`, `base_delay`, `max_delay`, `exponential_base`, `jitter`. All five are consumed, matching the Settings->Runtime config pattern.

### 4. Token System

TokenManager provides a clean high-level API over LandscapeRecorder:

```
Source Row -> create_initial_token() -> TokenInfo
                                          |
                            +---------+---+---+---------+
                            |         |       |         |
                          fork    coalesce  expand   update
                            |         |       |         |
                        children   merged  children  same token
```

**Key design decisions:**
- `deepcopy` for fork/expand prevents shared mutable state across branches
- Step resolution is injected via StepResolver (callers pass NodeID, not step)
- Atomic operations: fork and expand record parent outcome in the same recorder call
- Quarantine tokens get minimal OBSERVED contract for audit consistency

### 5. Trigger System

TriggerEvaluator implements "first to fire wins" with three trigger types:
- **Count:** Tracked by recording each accept, fire time latched when threshold reached
- **Timeout:** Computed deterministically from first_accept_time + timeout_seconds
- **Condition:** Expression-based, latched once fired (prevents unfiring of window-based conditions)

The evaluator collects all fired triggers with their fire times, sorts by time, and reports the earliest. This is correct for the "first to fire" semantic.

Checkpoint/restore preserves fire time offsets relative to first_accept_time, maintaining ordering correctness across resume.

### 6. Expression Parser

Two-phase design with clear security model:
1. Parse time: AST validation rejects forbidden constructs (fail-closed)
2. Runtime: Safe evaluation of validated AST against row data

**Whitelist approach:** Only explicitly allowed constructs pass validation. The custom `visit()` override rejects any unhandled expression node type, which is defense-in-depth against future Python AST additions.

**Allowed:** row access, safe builtins (len/str/int/float/bool/abs), comparisons, boolean ops, membership, ternary, arithmetic, literals.
**Forbidden:** function calls, lambda, comprehensions, assignment, await/yield, f-strings, attribute access (except row.get), arbitrary names.

### 7. Coalesce Executor

The most complex component. A stateful barrier with four policies and three merge strategies:

**Policies:** require_all, first, quorum, best_effort
**Merge strategies:** union (combine all fields), nested (branch as keys), select (pick one branch)

Key architectural patterns:
- Bounded completion tracking (FIFO eviction prevents OOM)
- Branch loss notifications for error-routed tokens
- Late arrival detection and rejection
- Contract propagation through merge (union merges contracts, nested creates new contract, select inherits)

### 8. Batch Adapter

Bridges synchronous orchestrator with asynchronous batch transforms:
- One SharedBatchAdapter per transform (owned by TransformExecutor)
- Multiple RowWaiters per adapter (one per in-flight row)
- (token_id, state_id) keying prevents stale results from reaching retry attempts
- ExceptionResult propagation ensures plugin bugs crash the orchestrator

### 9. Clock Abstraction

Minimal, correct abstraction. Protocol-based for structural typing. MockClock enables deterministic testing of timeout-dependent code. SystemClock wraps time.monotonic() for production.

### 10. Cross-Cutting Dependencies

```
                    contracts (types, enums, errors)
                        |
                  core.landscape.LandscapeRecorder
                        |
          +----+--------+--------+--------+
          |    |        |        |        |
       transform  gate   sink   aggregation  coalesce
          |    |        |        |        |
          +----+--------+--------+--------+
                        |
                  engine.spans.SpanFactory
                        |
                  engine.clock.Clock
```

**LandscapeRecorder** is the central dependency -- every executor requires it for audit recording.
**SpanFactory** is used by all executors for tracing.
**Clock** is used by triggers and coalesce for timeout evaluation.
**ExpressionParser** is used by gates and triggers.
**NodeStateGuard** is used by transform and aggregation executors.
**TokenManager** is used by gate (for fork) and coalesce (for merge).
**StepResolver** is injected into all executors via constructor.

### 11. Concerns and Recommendations (Ranked by Severity)

**P3 -- Low:**

1. **GateExecutor should use NodeStateGuard.** The manual begin/complete pattern with three try/except blocks is the exact anti-pattern that NodeStateGuard was designed to eliminate. Refactoring would improve consistency and reduce the risk of orphan OPEN states if new code paths are added.

2. **TokenManager.payload_store is dead code (tokens.py line 61).** The `payload_store` parameter is accepted, stored, but never used. The docstring acknowledges payload persistence moved to LandscapeRecorder. The parameter and instance variable should be removed.

3. **Truthiness checks in spans.py (lines 173, 174, 213-215, 254-258).** Uses `if node_id:` instead of `if node_id is not None:` for string parameters. While empty strings are unlikely for node_ids, the CLAUDE.md manifesto prefers explicit None checks. These should be changed to `is not None` for consistency.

4. **`_last_union_collisions` side-channel in coalesce_executor.py (line 151).** `_merge_data()` communicates collision info to `_execute_merge()` via an instance variable instead of a return value. This is a coupling smell that could be cleaned up by returning a tuple from `_merge_data()`.

**Observations (not actionable, for context):**

- The executor layer is mature and well-tested. Bug-fix references (P1, P2 tickets) throughout the code indicate these files have been battle-tested.
- The layered audit model (node_state per token, routing events per gate decision, batch lifecycle per aggregation) is comprehensive.
- The "durability before checkpoint" invariant in SinkExecutor is critical and correctly implemented.
- The split between "plugin error = legitimate failure, route to error sink" and "plugin exception = bug, crash immediately" is consistently enforced across all executors.

### 12. Confidence

**High.** The engine execution layer is architecturally sound, with clear separation of concerns, consistent audit patterns, and well-documented invariants. The concerns identified are all low-severity consistency issues. The code has clearly been through multiple rounds of hardening (evidence: extensive bug-fix references, NodeStateGuard introduction, consolidated state refactoring, bounded memory patterns). No structural defects or audit integrity gaps were identified.
