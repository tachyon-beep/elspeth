"""CoalesceExecutor: Merges tokens from parallel fork paths.

Coalesce is a stateful barrier that holds tokens until merge conditions are met.
Tokens are correlated by row_id (same source row that was forked).
"""

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from elspeth.contracts import TokenInfo
from elspeth.contracts.coalesce_checkpoint import (
    CoalesceCheckpointState,
    CoalescePendingCheckpoint,
    CoalesceTokenCheckpoint,
)
from elspeth.contracts.coalesce_metadata import ArrivalOrderEntry, CoalesceMetadata
from elspeth.contracts.enums import NodeStateStatus, RowOutcome
from elspeth.contracts.errors import CoalesceFailureReason, OrchestrationInvariantError
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.contracts.types import NodeID, StepResolver
from elspeth.core.config import CoalesceSettings
from elspeth.core.landscape import LandscapeRecorder
from elspeth.engine.clock import DEFAULT_CLOCK
from elspeth.engine.spans import SpanFactory

if TYPE_CHECKING:
    from elspeth.engine.clock import Clock
    from elspeth.engine.tokens import TokenManager

slog = structlog.get_logger(__name__)

COALESCE_CHECKPOINT_VERSION = "1.0"


@dataclass
class CoalesceOutcome:
    """Result of a coalesce accept operation.

    Attributes:
        held: True if token is being held waiting for more branches
        merged_token: The merged token if merge is complete, None if held
        consumed_tokens: Tokens that were merged (marked COALESCED)
        coalesce_metadata: Audit metadata about the merge (branches, policy, etc.)
        failure_reason: Reason for failure if merge failed (timeout, missing branches)
        coalesce_name: Name of the coalesce point that produced this outcome
        outcomes_recorded: True if terminal outcomes were already recorded by executor.
            When True, caller MUST NOT record outcomes again (Bug 9z8 fix).
    """

    held: bool
    merged_token: TokenInfo | None = None
    consumed_tokens: list[TokenInfo] = field(default_factory=list)
    coalesce_metadata: CoalesceMetadata | None = None
    failure_reason: str | None = None
    coalesce_name: str | None = None
    outcomes_recorded: bool = False


@dataclass(frozen=True, slots=True)
class _BranchEntry:
    """Per-branch state within a pending coalesce.

    Groups token, arrival time, and audit state_id that were previously
    scattered across three parallel dicts.  Frozen to prevent mutation
    after construction — a new entry is created per branch arrival.
    """

    token: TokenInfo
    arrival_time: float  # Monotonic timestamp of arrival
    state_id: str  # Landscape node_state ID for pending hold


@dataclass
class _PendingCoalesce:
    """Tracks pending tokens for a single row_id at a coalesce point."""

    branches: dict[str, _BranchEntry]  # branch_name -> entry
    first_arrival: float  # For timeout calculation
    lost_branches: dict[str, str] = field(default_factory=dict)  # branch_name -> loss reason


class CoalesceExecutor:
    """Executes coalesce operations with audit recording.

    Maintains state for pending coalesce operations:
    - Tracks which tokens have arrived for each row_id
    - Evaluates merge conditions based on policy
    - Merges row data according to strategy
    - Records audit trail via LandscapeRecorder

    Example:
        executor = CoalesceExecutor(recorder, span_factory, token_manager, run_id, step_resolver)

        # Configure coalesce point
        executor.register_coalesce(settings, node_id)

        # Accept tokens as they arrive
        for token in arriving_tokens:
            outcome = executor.accept(token, "coalesce_name")
            if outcome.merged_token:
                # Merged token continues through pipeline
                work_queue.append(outcome.merged_token)
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        span_factory: SpanFactory,
        token_manager: "TokenManager",
        run_id: str,
        step_resolver: StepResolver,
        clock: "Clock | None" = None,
        max_completed_keys: int = 10000,
    ) -> None:
        """Initialize executor.

        Args:
            recorder: Landscape recorder for audit trail
            span_factory: Span factory for tracing
            token_manager: TokenManager for creating merged tokens
            run_id: Run identifier for audit context
            step_resolver: Resolves NodeID to 1-indexed audit step position.
                           Injected at construction to eliminate step_in_pipeline
                           threading through public method signatures.
            clock: Optional clock for time access. Defaults to system clock.
                   Inject MockClock for deterministic testing.
            max_completed_keys: Maximum late-arrival completion keys retained in memory.
        """
        if max_completed_keys <= 0:
            raise OrchestrationInvariantError(f"max_completed_keys must be > 0, got {max_completed_keys}")

        self._recorder = recorder
        self._spans = span_factory
        self._token_manager = token_manager
        self._run_id = run_id
        self._step_resolver = step_resolver
        self._clock = clock if clock is not None else DEFAULT_CLOCK

        # Coalesce configuration: name -> settings
        self._settings: dict[str, CoalesceSettings] = {}
        # Node IDs: coalesce_name -> node_id
        self._node_ids: dict[str, NodeID] = {}
        # Pending tokens: (coalesce_name, row_id) -> _PendingCoalesce
        self._pending: dict[tuple[str, str], _PendingCoalesce] = {}
        # Completed coalesces: tracks keys that have already merged/failed
        # Used to detect late arrivals after merge and reject them gracefully
        # Uses OrderedDict as bounded FIFO set to prevent unbounded memory growth
        # (values are None, we only care about key presence and insertion order)
        self._completed_keys: OrderedDict[tuple[str, str], None] = OrderedDict()
        # Maximum completed keys to retain (prevents OOM in long-running pipelines).
        # Configurable to match source cardinality and memory budget.
        self._max_completed_keys: int = max_completed_keys
        # Temporary storage for union merge collision info (consumed by _execute_merge)
        self._last_union_collisions: dict[str, list[str]] = {}

    def register_coalesce(
        self,
        settings: CoalesceSettings,
        node_id: NodeID,
    ) -> None:
        """Register a coalesce point.

        Args:
            settings: Coalesce configuration
            node_id: Node ID assigned by orchestrator
        """
        self._settings[settings.name] = settings
        self._node_ids[settings.name] = node_id

    def get_registered_names(self) -> list[str]:
        """Get names of all registered coalesce points.

        Used by processor for timeout checking loop.

        Returns:
            List of registered coalesce names
        """
        return list(self._settings.keys())

    def get_checkpoint_state(self) -> CoalesceCheckpointState:
        """Return checkpoint state for pending coalesces."""
        from elspeth.core.checkpoint.serialization import checkpoint_dumps

        pending_entries: list[CoalescePendingCheckpoint] = []
        for (coalesce_name, row_id), pending in self._pending.items():
            branch_entries = {
                branch_name: CoalesceTokenCheckpoint(
                    token_id=entry.token.token_id,
                    row_id=entry.token.row_id,
                    branch_name=branch_name,
                    fork_group_id=entry.token.fork_group_id,
                    join_group_id=entry.token.join_group_id,
                    expand_group_id=entry.token.expand_group_id,
                    row_data=entry.token.row_data.to_dict(),
                    contract=entry.token.row_data.contract.to_checkpoint_format(),
                    state_id=entry.state_id,
                    arrival_offset_seconds=entry.arrival_time - pending.first_arrival,
                )
                for branch_name, entry in pending.branches.items()
            }
            pending_entries.append(
                CoalescePendingCheckpoint(
                    coalesce_name=coalesce_name,
                    row_id=row_id,
                    elapsed_age_seconds=self._clock.monotonic() - pending.first_arrival,
                    branches=branch_entries,
                    lost_branches=dict(pending.lost_branches),
                )
            )

        checkpoint = CoalesceCheckpointState(
            version=COALESCE_CHECKPOINT_VERSION,
            pending=tuple(pending_entries),
        )

        serialized = checkpoint_dumps(checkpoint.to_dict())
        size_mb = len(serialized) / 1_000_000
        if size_mb > 1:
            slog.warning(
                "large_coalesce_checkpoint",
                size_mb=size_mb,
                pending_count=len(pending_entries),
            )
        if size_mb > 10:
            raise RuntimeError(
                f"Coalesce checkpoint size {size_mb:.1f}MB exceeds 10MB limit. "
                f"Pending joins: {len(pending_entries)}."
            )

        return checkpoint

    def restore_from_checkpoint(self, state: CoalesceCheckpointState) -> None:
        """Restore pending coalesces from checkpoint."""
        if state.version != COALESCE_CHECKPOINT_VERSION:
            slog.warning(
                "coalesce_checkpoint_version_rejected",
                found_version=state.version,
                expected_version=COALESCE_CHECKPOINT_VERSION,
            )
            raise ValueError(
                f"Incompatible coalesce checkpoint version: {state.version!r}. "
                f"Expected: {COALESCE_CHECKPOINT_VERSION!r}."
            )

        now = self._clock.monotonic()
        self._pending.clear()
        self._completed_keys.clear()

        for pending_entry in state.pending:
            if pending_entry.coalesce_name not in self._settings:
                raise ValueError(
                    f"Checkpoint references unknown coalesce '{pending_entry.coalesce_name}'. "
                    f"Configured coalesces: {sorted(self._settings)}"
                )
            first_arrival = now - pending_entry.elapsed_age_seconds
            branches: dict[str, _BranchEntry] = {}
            for branch_name, token_checkpoint in pending_entry.branches.items():
                restored_contract = SchemaContract.from_checkpoint(token_checkpoint.contract)
                restored_row = PipelineRow(token_checkpoint.row_data, restored_contract)
                token = TokenInfo(
                    row_id=token_checkpoint.row_id,
                    token_id=token_checkpoint.token_id,
                    row_data=restored_row,
                    branch_name=token_checkpoint.branch_name,
                    fork_group_id=token_checkpoint.fork_group_id,
                    join_group_id=token_checkpoint.join_group_id,
                    expand_group_id=token_checkpoint.expand_group_id,
                )
                branches[branch_name] = _BranchEntry(
                    token=token,
                    arrival_time=first_arrival + token_checkpoint.arrival_offset_seconds,
                    state_id=token_checkpoint.state_id,
                )

            self._pending[(pending_entry.coalesce_name, pending_entry.row_id)] = _PendingCoalesce(
                branches=branches,
                first_arrival=first_arrival,
                lost_branches=dict(pending_entry.lost_branches),
            )

    def _mark_completed(self, key: tuple[str, str]) -> None:
        """Mark a coalesce key as completed with bounded memory.

        Uses FIFO eviction to prevent unbounded memory growth in long-running
        pipelines. When max capacity is exceeded, oldest entries are removed.
        Late arrivals after eviction will create new pending entries which
        timeout or flush correctly - acceptable trade-off vs OOM.

        Args:
            key: (coalesce_name, row_id) tuple to mark as completed
        """
        self._completed_keys[key] = None
        # Evict oldest entries if over capacity
        evicted_keys: list[tuple[str, str]] = []
        while len(self._completed_keys) > self._max_completed_keys:
            evicted_key, _ = self._completed_keys.popitem(last=False)
            evicted_keys.append(evicted_key)
        if evicted_keys:
            slog.warning(
                "coalesce_completed_keys_evicted",
                max_completed_keys=self._max_completed_keys,
                evicted_count=len(evicted_keys),
                oldest_evicted=evicted_keys[0],
                newest_evicted=evicted_keys[-1],
                retained_count=len(self._completed_keys),
            )

    def accept(
        self,
        token: TokenInfo,
        coalesce_name: str,
    ) -> CoalesceOutcome:
        """Accept a token at a coalesce point.

        If merge conditions are met, returns the merged token.
        Otherwise, holds the token and returns held=True.

        Step position is resolved internally via the injected StepResolver
        from the coalesce point's registered node_id.

        Args:
            token: Token arriving at coalesce point (must have branch_name)
            coalesce_name: Name of the coalesce configuration

        Returns:
            CoalesceOutcome indicating whether token was held or merged

        Raises:
            ValueError: If coalesce_name not registered or token has no branch_name
        """
        if coalesce_name not in self._settings:
            raise ValueError(f"Coalesce '{coalesce_name}' not registered")

        if token.branch_name is None:
            raise ValueError(f"Token {token.token_id} has no branch_name - only forked tokens can be coalesced")

        settings = self._settings[coalesce_name]
        node_id = self._node_ids[coalesce_name]
        step = self._step_resolver(node_id)

        # Validate branch is expected
        if token.branch_name not in settings.branches:
            raise ValueError(
                f"Token branch '{token.branch_name}' not in expected branches for coalesce '{coalesce_name}': {settings.branches}"
            )

        # Get or create pending state for this row
        key = (coalesce_name, token.row_id)
        now = self._clock.monotonic()

        # Check if this coalesce already completed (late arrival)
        if key in self._completed_keys:
            # Late arrival after merge/failure already happened
            # Record failure audit trail for this late token
            failure_reason = "late_arrival_after_merge"
            error_hash = hashlib.sha256(failure_reason.encode()).hexdigest()[:16]
            state = self._recorder.begin_node_state(
                token_id=token.token_id,
                node_id=node_id,
                run_id=self._run_id,
                step_index=step,
                input_data=token.row_data.to_dict(),  # Recorder expects dict
            )
            error = CoalesceFailureReason(
                failure_reason=failure_reason,
                expected_branches=tuple(settings.branches),
                branches_arrived=(),  # Late arrival — merge already happened
                merge_policy=settings.merge,
            )
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.FAILED,
                error=error,
                duration_ms=0,
            )
            self._recorder.record_token_outcome(
                run_id=self._run_id,
                token_id=token.token_id,
                outcome=RowOutcome.FAILED,
                error_hash=error_hash,
            )

            # Return failure outcome
            return CoalesceOutcome(
                held=False,
                failure_reason=failure_reason,
                consumed_tokens=[token],
                coalesce_metadata=CoalesceMetadata.for_late_arrival(
                    policy=settings.policy,
                    reason="Siblings already merged/failed, this token arrived too late",
                ),
                coalesce_name=coalesce_name,
                outcomes_recorded=True,
            )

        if key not in self._pending:
            self._pending[key] = _PendingCoalesce(
                branches={},
                first_arrival=now,
            )

        pending = self._pending[key]

        # Detect duplicate arrivals (indicates bug in upstream code)
        # Per "Plugin Ownership" principle: bugs in our code should crash, not hide
        if token.branch_name in pending.branches:
            existing = pending.branches[token.branch_name]
            raise ValueError(
                f"Duplicate arrival for branch '{token.branch_name}' at coalesce '{coalesce_name}'. "
                f"Existing token: {existing.token.token_id}, new token: {token.token_id}. "
                f"This indicates a bug in fork, retry, or checkpoint/resume logic."
            )

        # Record pending node state for audit trail FIRST,
        # then store entry atomically (all per-branch state in one assignment)
        state = self._recorder.begin_node_state(
            token_id=token.token_id,
            node_id=node_id,
            run_id=self._run_id,
            step_index=step,
            input_data=token.row_data.to_dict(),  # Recorder expects dict
        )
        pending.branches[token.branch_name] = _BranchEntry(
            token=token,
            arrival_time=now,
            state_id=state.state_id,
        )

        # Check if merge conditions are met
        if self._should_merge(settings, pending):
            return self._execute_merge(
                settings=settings,
                node_id=node_id,
                pending=pending,
                step=step,
                key=key,
                coalesce_name=coalesce_name,
            )

        # Hold token - audit trail already recorded above
        return CoalesceOutcome(held=True, coalesce_name=coalesce_name)

    def _should_merge(
        self,
        settings: CoalesceSettings,
        pending: _PendingCoalesce,
    ) -> bool:
        """Check if merge conditions are met based on policy."""
        arrived_count = len(pending.branches)
        expected_count = len(settings.branches)

        if settings.policy == "require_all":
            return arrived_count == expected_count

        elif settings.policy == "first":
            return arrived_count >= 1

        elif settings.policy == "quorum":
            if settings.quorum_count is None:
                raise RuntimeError(
                    f"quorum_count is None for quorum policy at coalesce '{settings.name}'. This indicates a config validation bug."
                )
            return arrived_count >= settings.quorum_count

        # settings.policy == "best_effort":
        # Merge on timeout (checked elsewhere) or when all branches accounted for.
        # Lost branches count as "accounted for" — they won't arrive but we know about them.
        accounted_count = arrived_count + len(pending.lost_branches)
        return accounted_count >= expected_count

    def _fail_pending(
        self,
        settings: CoalesceSettings,
        key: tuple[str, str],
        step: int,
        failure_reason: str,
        *,
        is_timeout: bool = False,
    ) -> CoalesceOutcome:
        """Fail all arrived tokens in a pending coalesce and clean up.

        Shared helper used by check_timeouts(), flush_pending(), and
        _evaluate_after_loss() to avoid duplicating failure recording logic.

        Args:
            settings: Coalesce settings for metadata
            key: (coalesce_name, row_id) tuple
            step: Resolved audit step index for the coalesce node
            failure_reason: Machine-readable failure reason string
            is_timeout: Whether this failure was triggered by a timeout.
                Callers set this explicitly rather than inferring from the
                failure_reason string.

        Returns:
            CoalesceOutcome with failure_reason set and outcomes_recorded=True
        """
        coalesce_name = key[0]
        pending = self._pending[key]
        consumed_tokens = [e.token for e in pending.branches.values()]
        error_hash = hashlib.sha256(failure_reason.encode()).hexdigest()[:16]
        now = self._clock.monotonic()

        # Complete pending node states with failure
        error = CoalesceFailureReason(
            failure_reason=failure_reason,
            expected_branches=tuple(settings.branches),
            branches_arrived=tuple(pending.branches.keys()),
            merge_policy=settings.merge,
            timeout_ms=int(settings.timeout_seconds * 1000) if is_timeout and settings.timeout_seconds is not None else None,
        )
        for _branch_name, entry in pending.branches.items():
            self._recorder.complete_node_state(
                state_id=entry.state_id,
                status=NodeStateStatus.FAILED,
                error=error,
                duration_ms=(now - entry.arrival_time) * 1000,
            )
            self._recorder.record_token_outcome(
                run_id=self._run_id,
                token_id=entry.token.token_id,
                outcome=RowOutcome.FAILED,
                error_hash=error_hash,
            )

        del self._pending[key]
        self._mark_completed(key)

        return CoalesceOutcome(
            held=False,
            failure_reason=failure_reason,
            consumed_tokens=consumed_tokens,
            coalesce_metadata=CoalesceMetadata.for_failure(
                policy=settings.policy,
                expected_branches=tuple(settings.branches),
                branches_arrived=tuple(pending.branches.keys()),
                branches_lost=pending.lost_branches if pending.lost_branches else None,
                quorum_required=settings.quorum_count,
                timeout_seconds=settings.timeout_seconds,
            ),
            coalesce_name=coalesce_name,
            outcomes_recorded=True,
        )

    def _execute_merge(
        self,
        settings: CoalesceSettings,
        node_id: NodeID,
        pending: _PendingCoalesce,
        step: int,
        key: tuple[str, str],
        coalesce_name: str,
    ) -> CoalesceOutcome:
        """Execute the merge and create merged token."""
        now = self._clock.monotonic()

        # ─────────────────────────────────────────────────────────────────────
        # Defensive check: crash if any token has no contract
        # Per CLAUDE.md: "Bad data in the audit trail = crash immediately"
        # A token with None contract is a bug in upstream code (fork/transform).
        # ─────────────────────────────────────────────────────────────────────
        for branch, entry in pending.branches.items():
            if entry.token.row_data.contract is None:
                raise ValueError(
                    f"Token {entry.token.token_id} on branch '{branch}' has no contract. "
                    f"Cannot coalesce without contracts on all parents. "
                    f"This indicates a bug in fork or transform execution."
                )

        # Validate select_branch is present for select merge strategy
        # (Bug 2ho fix: reject instead of silent fallback)
        if settings.merge == "select" and settings.select_branch not in pending.branches:
            # select_branch not arrived - this is a failure, not a fallback
            consumed_tokens = [e.token for e in pending.branches.values()]
            error_msg = "select_branch_not_arrived"
            error_hash = hashlib.sha256(error_msg.encode()).hexdigest()[:16]

            select_error = CoalesceFailureReason(
                failure_reason="select_branch_not_arrived",
                expected_branches=tuple(settings.branches),
                branches_arrived=tuple(pending.branches.keys()),
                merge_policy=settings.merge,
                select_branch=settings.select_branch,
            )
            for _branch_name, entry in pending.branches.items():
                self._recorder.complete_node_state(
                    state_id=entry.state_id,
                    status=NodeStateStatus.FAILED,
                    error=select_error,
                    duration_ms=(now - entry.arrival_time) * 1000,
                )
                self._recorder.record_token_outcome(
                    run_id=self._run_id,
                    token_id=entry.token.token_id,
                    outcome=RowOutcome.FAILED,
                    error_hash=error_hash,
                )

            del self._pending[key]
            self._mark_completed(key)
            return CoalesceOutcome(
                held=False,
                failure_reason="select_branch_not_arrived",
                consumed_tokens=consumed_tokens,
                coalesce_metadata=CoalesceMetadata.for_select_not_arrived(
                    policy=settings.policy,
                    merge_strategy=settings.merge,
                    # select_branch is validated non-None by CoalesceSettings for merge="select"
                    select_branch=settings.select_branch,  # type: ignore[arg-type]
                    branches_arrived=tuple(pending.branches.keys()),
                ),
                coalesce_name=coalesce_name,
                outcomes_recorded=True,  # Bug 9z8 fix: token outcomes already recorded above
            )

        # ─────────────────────────────────────────────────────────────────────
        # Merge row data according to strategy (returns dict)
        # We do this FIRST so we can derive contract from actual data shape
        # ─────────────────────────────────────────────────────────────────────
        merged_data_dict = self._merge_data(settings, pending.branches)

        # ─────────────────────────────────────────────────────────────────────
        # Build contract based on merge strategy and actual data shape
        # ─────────────────────────────────────────────────────────────────────
        contracts: list[SchemaContract] = [e.token.row_data.contract for e in pending.branches.values()]

        if settings.merge == "union":
            # Union: Merge all contracts (current behavior - correct)
            merged_contract = contracts[0]
            for c in contracts[1:]:
                try:
                    merged_contract = merged_contract.merge(c)
                except Exception as e:
                    # Contract merge failure is an orchestration invariant violation
                    # Contracts with conflicting types cannot be merged
                    slog.error(
                        "contract_merge_failed",
                        coalesce_name=coalesce_name,
                        branches=list(pending.branches.keys()),
                        error=str(e),
                    )
                    raise OrchestrationInvariantError(
                        f"Contract merge failed at coalesce point '{coalesce_name}'. Branches: {list(pending.branches.keys())}. Error: {e}"
                    ) from e

            slog.info(
                "contract_merge_success",
                coalesce_name=coalesce_name,
                merge_strategy="union",
                branch_count=len(pending.branches),
                branches=list(pending.branches.keys()),
            )

        elif settings.merge == "nested":
            # Nested: Contract declares branch keys with object type
            # Data shape is {branch_a: {...}, branch_b: {...}} where each value
            # is the full row data from that branch as a plain dict.
            # We use object (the "any" type in VALID_FIELD_TYPES) because dict
            # is not a valid FieldContract type and the contract only needs to
            # declare that the field exists, not constrain its inner structure.
            branch_fields = tuple(
                FieldContract(
                    original_name=branch_name,
                    normalized_name=branch_name,
                    python_type=object,
                    required=branch_name in pending.branches,
                    source="declared",
                )
                for branch_name in settings.branches
            )
            merged_contract = SchemaContract(
                fields=branch_fields,
                mode="FIXED",
                locked=True,
            )

            slog.info(
                "contract_created_for_nested_merge",
                coalesce_name=coalesce_name,
                merge_strategy="nested",
                branch_count=len(pending.branches),
                branches=list(pending.branches.keys()),
                output_keys=list(merged_data_dict.keys()),
            )

        elif settings.merge == "select":
            # Select: Use selected branch's contract directly (data has only those fields)
            # Find the selected branch's contract
            if settings.select_branch is None:
                raise RuntimeError(
                    f"select_branch is None for select merge strategy at coalesce '{settings.name}'. This indicates a config validation bug."
                )

            # Get the token for the selected branch
            selected_entry = pending.branches[settings.select_branch]
            merged_contract = selected_entry.token.row_data.contract

            slog.info(
                "contract_from_selected_branch",
                coalesce_name=coalesce_name,
                merge_strategy="select",
                selected_branch=settings.select_branch,
                branches_arrived=tuple(pending.branches.keys()),
            )

        else:
            # Unreachable - config validation ensures merge is one of the above
            raise RuntimeError(f"Unknown merge strategy: {settings.merge}")

        # Create PipelineRow with strategy-appropriate contract
        merged_data = PipelineRow(merged_data_dict, merged_contract)

        # Get list of consumed tokens
        consumed_tokens = [e.token for e in pending.branches.values()]

        # Create merged token via TokenManager
        merged_token = self._token_manager.coalesce_tokens(
            parents=consumed_tokens,
            merged_data=merged_data,
            node_id=node_id,
        )

        # Build audit metadata BEFORE completing node states (Bug l4h fix)
        # This allows us to include it in context_after for each consumed token
        coalesce_metadata = CoalesceMetadata.for_merge(
            policy=settings.policy,
            merge_strategy=settings.merge,
            expected_branches=tuple(settings.branches),
            branches_arrived=tuple(pending.branches.keys()),
            branches_lost=pending.lost_branches if pending.lost_branches else {},
            arrival_order=[
                ArrivalOrderEntry(
                    branch=branch,
                    arrival_offset_ms=(entry.arrival_time - pending.first_arrival) * 1000,
                )
                for branch, entry in sorted(pending.branches.items(), key=lambda x: x[1].arrival_time)
            ],
            wait_duration_ms=(now - pending.first_arrival) * 1000,
        )

        # Include union merge collision info in audit trail if present
        if self._last_union_collisions:
            coalesce_metadata = CoalesceMetadata.with_collisions(coalesce_metadata, self._last_union_collisions)
            self._last_union_collisions = {}

        # Complete pending node states for consumed tokens
        # (These states were created as "pending" when tokens were held in accept())
        for _branch_name, entry in pending.branches.items():
            # Complete it now that merge is happening
            # Bug l4h fix: include coalesce metadata in context_after for audit trail
            self._recorder.complete_node_state(
                state_id=entry.state_id,
                status=NodeStateStatus.COMPLETED,
                output_data={"merged_into": merged_token.token_id},
                duration_ms=(now - entry.arrival_time) * 1000,
                context_after=coalesce_metadata,
            )

            # Record terminal token outcome (COALESCED)
            self._recorder.record_token_outcome(
                run_id=self._run_id,
                token_id=entry.token.token_id,
                outcome=RowOutcome.COALESCED,
                join_group_id=merged_token.join_group_id,
            )

        # NOTE: The merged token does NOT get COALESCED recorded here.
        # - Consumed tokens: COALESCED (terminal) - they've been absorbed into the merge
        # - Merged token: Will get COMPLETED when it reaches a sink, or COALESCED if
        #   consumed by an outer coalesce (nested coalesce scenario)
        # Recording COALESCED for merged token here would break nested coalesces where
        # the inner merge result becomes a consumed token in the outer merge.

        # Clean up pending state and mark as completed
        del self._pending[key]
        self._mark_completed(key)  # Track completion to reject late arrivals (bounded)

        return CoalesceOutcome(
            held=False,
            merged_token=merged_token,
            consumed_tokens=consumed_tokens,
            coalesce_metadata=coalesce_metadata,
            coalesce_name=coalesce_name,
        )

    def _merge_data(
        self,
        settings: CoalesceSettings,
        branches: dict[str, _BranchEntry],
    ) -> dict[str, Any]:
        """Merge row data from arrived tokens based on strategy.

        Note: row_data is PipelineRow, so we use to_dict() to get raw dict.
        """
        if settings.merge == "union":
            # Combine all fields from all branches.
            # On name collision, the last branch in settings.branches wins.
            # Collisions are recorded in the audit trail (coalesce_metadata)
            # so that overwritten values are never silently lost.
            merged: dict[str, Any] = {}
            field_origins: dict[str, str] = {}  # field -> branch that set it
            collisions: dict[str, list[str]] = {}  # field -> [branch1, branch2, ...]
            for branch_name in settings.branches:
                if branch_name in branches:
                    branch_data = branches[branch_name].token.row_data.to_dict()
                    for field in branch_data:
                        if field in field_origins:
                            if field not in collisions:
                                collisions[field] = [field_origins[field]]
                            collisions[field].append(branch_name)
                        field_origins[field] = branch_name
                    merged.update(branch_data)
            if collisions:
                slog.warning(
                    "union_merge_field_collisions",
                    collisions=dict(collisions),
                    winner_branch={f: branches_list[-1] for f, branches_list in collisions.items()},
                )
            # Stash collisions for audit metadata (read by _execute_merge)
            self._last_union_collisions = collisions
            return merged

        elif settings.merge == "nested":
            # Each branch as nested object (use to_dict() for serializable dict)
            return {
                branch_name: branches[branch_name].token.row_data.to_dict() for branch_name in settings.branches if branch_name in branches
            }

        # settings.merge == "select":
        # Take specific branch output
        # Note: _execute_merge validates select_branch presence before calling this method
        # If we get here without select_branch, it's a bug in our code
        if settings.select_branch is None:
            raise RuntimeError(
                f"select_branch is None for select merge strategy at coalesce '{settings.name}'. This indicates a config validation bug."
            )
        if settings.select_branch not in branches:
            # This should be unreachable - _execute_merge catches this case first
            # Per "Plugin Ownership" principle: crash on our bugs, don't hide them
            raise RuntimeError(
                f"select_branch '{settings.select_branch}' not in arrived branches {list(branches.keys())}. "
                f"This indicates a bug in _execute_merge validation (Bug 2ho fix should have caught this)."
            )
        # Return copy of dict (to_dict() returns a copy already)
        return branches[settings.select_branch].token.row_data.to_dict()

    def check_timeouts(
        self,
        coalesce_name: str,
    ) -> list[CoalesceOutcome]:
        """Check for timed-out pending coalesces and merge them.

        For best_effort policy, merges whatever has arrived when timeout expires.
        For quorum policy with timeout, merges if quorum met when timeout expires.

        Step position is resolved internally via the injected StepResolver
        from the coalesce point's registered node_id.

        Args:
            coalesce_name: Name of the coalesce configuration

        Returns:
            List of CoalesceOutcomes for any merges triggered by timeout
        """
        if coalesce_name not in self._settings:
            raise ValueError(f"Coalesce '{coalesce_name}' not registered")

        settings = self._settings[coalesce_name]
        node_id = self._node_ids[coalesce_name]
        step = self._step_resolver(node_id)

        if settings.timeout_seconds is None:
            return []

        now = self._clock.monotonic()
        results: list[CoalesceOutcome] = []
        keys_to_process: list[tuple[str, str]] = []

        # Find timed-out entries
        for key, pending in self._pending.items():
            if key[0] != coalesce_name:
                continue

            elapsed = now - pending.first_arrival
            if elapsed >= settings.timeout_seconds:
                keys_to_process.append(key)

        # Process timed-out entries
        for key in keys_to_process:
            pending = self._pending[key]

            # For best_effort, merge on timeout if anything arrived, or fail if nothing arrived
            if settings.policy == "best_effort":
                if len(pending.branches) > 0:
                    outcome = self._execute_merge(
                        settings=settings,
                        node_id=node_id,
                        pending=pending,
                        step=step,
                        key=key,
                        coalesce_name=coalesce_name,
                    )
                    results.append(outcome)
                else:
                    # All branches lost, no arrivals — fail the coalesce
                    results.append(
                        self._fail_pending(
                            settings,
                            key,
                            step,
                            failure_reason="best_effort_timeout_no_arrivals",
                            is_timeout=True,
                        )
                    )

            # For quorum, merge on timeout only if quorum met
            elif settings.policy == "quorum":
                if settings.quorum_count is None:
                    raise RuntimeError(
                        f"quorum_count is None for quorum policy at coalesce '{settings.name}'. This indicates a config validation bug."
                    )
                if len(pending.branches) >= settings.quorum_count:
                    outcome = self._execute_merge(
                        settings=settings,
                        node_id=node_id,
                        pending=pending,
                        step=step,
                        key=key,
                        coalesce_name=coalesce_name,
                    )
                    results.append(outcome)
                else:
                    # Quorum not met at timeout - record failure
                    results.append(
                        self._fail_pending(
                            settings,
                            key,
                            step,
                            failure_reason="quorum_not_met_at_timeout",
                            is_timeout=True,
                        )
                    )

            # For require_all, timeout means incomplete - record failure
            # (Bug P1-2026-01-30 fix: require_all was missing from check_timeouts)
            elif settings.policy == "require_all":
                # require_all never does partial merge - timeout is always a failure
                results.append(
                    self._fail_pending(
                        settings,
                        key,
                        step,
                        failure_reason="incomplete_branches",
                        is_timeout=True,
                    )
                )

        return results

    def flush_pending(self) -> list[CoalesceOutcome]:
        """Flush all pending coalesces (called at end-of-source or shutdown).

        For best_effort policy: merges whatever arrived.
        For quorum policy: merges if quorum met, returns failure otherwise.
        For require_all policy: returns failure (never partial merge).
        For first policy: should never have pending (merges immediately).

        Step positions are resolved internally via the injected StepResolver
        from each coalesce point's registered node_id.

        Returns:
            List of CoalesceOutcomes for all pending coalesces
        """
        results: list[CoalesceOutcome] = []
        keys_to_process = list(self._pending.keys())

        for key in keys_to_process:
            coalesce_name, _row_id = key
            settings = self._settings[coalesce_name]
            node_id = self._node_ids[coalesce_name]
            pending = self._pending[key]
            step = self._step_resolver(node_id)

            if settings.policy == "best_effort":
                # Merge whatever arrived (or fail if nothing arrived)
                if len(pending.branches) > 0:
                    outcome = self._execute_merge(
                        settings=settings,
                        node_id=node_id,
                        pending=pending,
                        step=step,
                        key=key,
                        coalesce_name=coalesce_name,
                    )
                    results.append(outcome)
                elif pending.lost_branches:
                    # All branches lost — no data to merge
                    results.append(
                        self._fail_pending(
                            settings,
                            key,
                            step,
                            failure_reason="all_branches_lost",
                        )
                    )

            elif settings.policy == "quorum":
                if settings.quorum_count is None:
                    raise RuntimeError(
                        f"quorum_count is None for quorum policy at coalesce '{settings.name}'. This indicates a config validation bug."
                    )
                if len(pending.branches) >= settings.quorum_count:
                    outcome = self._execute_merge(
                        settings=settings,
                        node_id=node_id,
                        pending=pending,
                        step=step,
                        key=key,
                        coalesce_name=coalesce_name,
                    )
                    results.append(outcome)
                else:
                    # Quorum not met - record failure
                    results.append(
                        self._fail_pending(
                            settings,
                            key,
                            step,
                            failure_reason="quorum_not_met",
                        )
                    )

            elif settings.policy == "require_all":
                # require_all never does partial merge
                results.append(
                    self._fail_pending(
                        settings,
                        key,
                        step,
                        failure_reason="incomplete_branches",
                    )
                )

            elif settings.policy == "first":
                # first policy merges immediately on first arrival - pending entries indicate a bug
                raise RuntimeError(
                    f"Invariant violation: 'first' policy should never have pending entries. "
                    f"Found pending coalesce for row_id='{key[1]}' at '{coalesce_name}' with "
                    f"branches {list(pending.branches.keys())}. This indicates a bug in accept() logic."
                )

        # Clear completed keys to prevent unbounded memory growth
        # After flush, no more tokens will arrive (source ended), so late-arrival
        # detection is no longer needed. This prevents O(rows) memory accumulation
        # in long-running pipelines.
        self._completed_keys.clear()

        return results

    def notify_branch_lost(
        self,
        coalesce_name: str,
        row_id: str,
        lost_branch: str,
        reason: str,
    ) -> CoalesceOutcome | None:
        """Notify that a branch was error-routed and will never arrive.

        Called by the processor when a forked token is diverted to an error sink
        before reaching this coalesce point. Adjusts the expected branch count
        and re-evaluates merge conditions.

        Threading: CoalesceExecutor is single-threaded — called from the
        processor's synchronous work queue loop. The processor processes one
        work item at a time, so there is no concurrency within a single row's
        fork/coalesce lifecycle.

        Step position is resolved internally via the injected StepResolver
        from the coalesce point's registered node_id.

        Args:
            coalesce_name: Name of the coalesce configuration
            row_id: Source row ID (correlates forked tokens)
            lost_branch: Name of the branch that was error-routed
            reason: Machine-readable reason for the loss

        Returns:
            CoalesceOutcome if merge/failure triggered, None if still waiting.
        """
        if coalesce_name not in self._settings:
            raise ValueError(f"Coalesce '{coalesce_name}' not registered")

        key = (coalesce_name, row_id)

        # Already completed (race with normal merge) — ignore
        if key in self._completed_keys:
            return None

        settings = self._settings[coalesce_name]
        node_id = self._node_ids[coalesce_name]
        step = self._step_resolver(node_id)

        # Validate branch is expected
        if lost_branch not in settings.branches:
            raise ValueError(f"Lost branch '{lost_branch}' not in expected branches for coalesce '{coalesce_name}': {settings.branches}")

        # No pending entry yet — branch lost before ANY branch arrived.
        # Create a minimal pending entry with the loss recorded.
        if key not in self._pending:
            self._pending[key] = _PendingCoalesce(
                branches={},
                first_arrival=self._clock.monotonic(),
                lost_branches={lost_branch: reason},
            )
            return self._evaluate_after_loss(settings, key, step)

        pending = self._pending[key]

        # Validate branch hasn't already arrived (would be a processor bug)
        if lost_branch in pending.branches:
            raise ValueError(
                f"Branch '{lost_branch}' already arrived at coalesce '{coalesce_name}' "
                f"but was reported as lost. This indicates a bug in the processor — "
                f"a token cannot both arrive and be error-routed."
            )

        # Validate branch hasn't already been marked lost (would be a processor bug)
        if lost_branch in pending.lost_branches:
            raise ValueError(
                f"Branch '{lost_branch}' already marked lost at coalesce '{coalesce_name}'. "
                f"Duplicate loss notification indicates a processor bug."
            )

        # Record the loss and re-evaluate
        pending.lost_branches[lost_branch] = reason
        return self._evaluate_after_loss(settings, key, step)

    def _evaluate_after_loss(
        self,
        settings: CoalesceSettings,
        key: tuple[str, str],
        step: int,
    ) -> CoalesceOutcome | None:
        """Re-evaluate merge conditions after a branch loss notification.

        Policy-specific consequences:
        - require_all: ANY lost branch = immediate failure
        - quorum: fail if quorum is now impossible, merge if already met
        - best_effort: merge immediately if all branches accounted for
        - first: no action (should have merged on first arrival)

        Args:
            settings: Coalesce settings for the affected point
            key: (coalesce_name, row_id) tuple
            step: Resolved audit step index for the coalesce node

        Returns:
            CoalesceOutcome if merge/failure triggered, None if still waiting.
        """
        pending = self._pending[key]
        arrived_count = len(pending.branches)
        total_branches = len(settings.branches)
        lost_count = len(pending.lost_branches)

        if settings.policy == "require_all":
            # require_all: ANY lost branch = immediate failure
            return self._fail_pending(
                settings,
                key,
                step,
                failure_reason=f"branch_lost:{','.join(sorted(pending.lost_branches.keys()))}",
            )

        elif settings.policy == "quorum":
            if settings.quorum_count is None:
                raise RuntimeError(
                    f"quorum_count is None for quorum policy at coalesce '{settings.name}'. This indicates a config validation bug."
                )
            # Check if quorum is now impossible
            max_possible = total_branches - lost_count
            if max_possible < settings.quorum_count:
                return self._fail_pending(
                    settings,
                    key,
                    step,
                    failure_reason=f"quorum_impossible:need={settings.quorum_count},max_possible={max_possible}",
                )
            # Check if arrived count already meets quorum
            if arrived_count >= settings.quorum_count:
                node_id = self._node_ids[settings.name]
                return self._execute_merge(settings, node_id, pending, step, key, settings.name)
            return None  # Still waiting

        elif settings.policy == "best_effort":
            # All branches accounted for (arrived + lost)?
            if arrived_count + lost_count >= total_branches:
                if arrived_count > 0:
                    node_id = self._node_ids[settings.name]
                    return self._execute_merge(settings, node_id, pending, step, key, settings.name)
                return self._fail_pending(
                    settings,
                    key,
                    step,
                    failure_reason="all_branches_lost",
                )
            return None  # Still waiting for remaining branches

        # settings.policy == "first":
        # first: should already have merged on first arrival
        # If no arrivals yet, nothing to merge
        return None
