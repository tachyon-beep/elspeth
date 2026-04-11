"""SinkExecutor - wraps sink.write() with artifact recording."""

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from elspeth.contracts import (
    Artifact,
    ExecutionError,
    NodeStateOpen,
    PendingOutcome,
    RowOutcome,
    SinkProtocol,
    TokenInfo,
)
from elspeth.contracts.audit import TokenRef
from elspeth.contracts.diversion import SinkWriteResult
from elspeth.contracts.enums import NodeStateStatus, RoutingMode
from elspeth.contracts.errors import (
    TIER_1_ERRORS,
    AuditIntegrityError,
    FrameworkBugError,
    OrchestrationInvariantError,
    PluginContractViolation,
    SinkDiversionReason,
)
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.results import ArtifactDescriptor
from elspeth.contracts.schema_contract import SchemaContract
from elspeth.core.landscape.data_flow_repository import DataFlowRepository
from elspeth.core.landscape.execution_repository import ExecutionRepository
from elspeth.core.operations import track_operation
from elspeth.engine.spans import SpanFactory

logger = logging.getLogger(__name__)


class SinkExecutor:
    """Executes sinks with artifact recording.

    Wraps sink.write() with a three-phase flow:
    1. Call sink.write() inside track_operation (discover diversions)
    2. Open/complete node_states and record outcomes for primary tokens
    3. Route diverted tokens to failsink or discard with audit trail
    4. Register artifacts and emit OpenTelemetry span

    CRITICAL: Every token reaching a sink gets a node_state at the primary
    sink. Accepted rows get COMPLETED; diverted rows get FAILED (the row
    didn't reach its destination). Failsink-mode diverted tokens also get
    a second node_state at the failsink (COMPLETED — the row was written
    there). Discard-mode diverted tokens have only the primary FAILED state.

    Note: Unlike TransformExecutor/GateExecutor/AggregationExecutor, SinkExecutor
    does NOT use StepResolver. Sinks are not DAG processing nodes — their step is
    always max(processing_steps) + 1, computed by RowProcessor.resolve_sink_step()
    and passed as step_in_pipeline by the orchestrator. This is intentional: sinks
    exist after all processing nodes and have a fixed, deterministic step position.

    Example:
        executor = SinkExecutor(execution, data_flow, span_factory, run_id)
        artifact, diversion_count = executor.write(
            sink=my_sink,
            tokens=tokens_to_write,
            ctx=ctx,
            step_in_pipeline=5,
            sink_name="output",
            pending_outcome=pending,
        )
    """

    def __init__(
        self,
        execution: ExecutionRepository,
        data_flow: DataFlowRepository,
        span_factory: SpanFactory,
        run_id: str,
    ) -> None:
        """Initialize executor.

        Args:
            execution: Execution repository for node states, routing, artifacts
            data_flow: Data flow repository for token outcomes
            span_factory: Span factory for tracing
            run_id: Run identifier for artifact registration
        """
        self._execution = execution
        self._data_flow = data_flow
        self._spans = span_factory
        self._run_id = run_id

    def _complete_states_failed(
        self,
        *,
        states: list[tuple[TokenInfo, NodeStateOpen]],
        duration_ms: float,
        error: ExecutionError,
    ) -> None:
        """Complete all opened sink states as FAILED."""
        if not states:
            return
        per_token_ms = duration_ms / len(states)
        for _, state in states:
            self._execution.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=per_token_ms,
                error=error,
            )

    def _best_effort_cleanup(
        self,
        states: list[tuple[TokenInfo, NodeStateOpen]],
        original_error: Exception,
        phase: str,
    ) -> None:
        """Best-effort cleanup of OPEN states before re-raising a system error.

        On FrameworkBugError/AuditIntegrityError, the system is crashing. But
        leaving node_states permanently OPEN is itself a Tier 1 violation —
        they falsely claim "in progress" when no processing is happening.
        Attempt to close them as FAILED; if that also fails, log and let the
        original error propagate.
        """
        cleanup_error = ExecutionError(
            exception=str(original_error),
            exception_type=type(original_error).__name__,
            phase=phase,
        )
        try:
            self._complete_states_failed(
                states=states,
                duration_ms=0.0,
                error=cleanup_error,
            )
        except TIER_1_ERRORS:
            raise  # Audit corruption during cleanup is higher priority than original error
        except Exception as cleanup_exc:
            logger.warning(
                "Best-effort cleanup of %d OPEN states failed during %s crash — "
                "states may remain OPEN. Original error: %s. Cleanup error: %s: %s",
                len(states),
                type(original_error).__name__,
                original_error,
                type(cleanup_exc).__name__,
                cleanup_exc,
            )

    @staticmethod
    def _validate_sink_input(
        sink: SinkProtocol,
        rows: list[dict[str, object]],
        *,
        skip_schema: bool = False,
        contracts: list[SchemaContract] | None = None,
    ) -> None:
        """Validate rows against a sink's input schema and required fields.

        Args:
            sink: Sink to validate against.
            rows: Row dicts to validate.
            skip_schema: If True, skip input_schema.model_validate() and only
                check required fields. Used for failsink validation where the
                executor injects enrichment fields (__diversion_*) that are
                outside the failsink's declared schema.
            contracts: Optional per-row SchemaContracts for context-aware error
                messages. When provided, a missing-field error annotates any
                field that is optional in the row's contract, pointing at
                coalesce merge as the likely root cause.
        """
        if not skip_schema:
            for row in rows:
                try:
                    sink.input_schema.model_validate(row)
                except ValidationError as e:
                    raise PluginContractViolation(
                        f"Sink '{sink.name}' input validation failed: {e}. This indicates an upstream transform/source schema bug."
                    ) from e

        if sink.declared_required_fields:
            for row_index, row in enumerate(rows):
                missing = sorted(f for f in sink.declared_required_fields if f not in row)
                if missing:
                    # If a contract is available, annotate missing fields that are
                    # marked optional in the contract (coalesce merge artifact).
                    contract_context = ""
                    if contracts is not None and row_index < len(contracts):
                        contract = contracts[row_index]
                        contract_field_names = {fc.normalized_name for fc in contract.fields}
                        optional_in_contract = [f for f in missing if f in contract_field_names and f not in contract.required_field_names]
                        if optional_in_contract:
                            contract_context = (
                                f" Fields {optional_in_contract} are optional in the row's "
                                f"schema contract (likely from coalesce merge). "
                                f"Fix: ensure all branches produce these fields as required."
                            )
                    raise PluginContractViolation(
                        f"Sink '{sink.name}' row {row_index} is missing required fields "
                        f"{missing}. This indicates an upstream transform/schema bug.{contract_context}"
                    )

    def write(
        self,
        sink: SinkProtocol,
        tokens: list[TokenInfo],
        ctx: PluginContext,
        step_in_pipeline: int,
        *,
        sink_name: str,
        pending_outcome: PendingOutcome | None,
        failsink: SinkProtocol | None = None,
        failsink_name: str | None = None,
        failsink_edge_id: str | None = None,
        on_token_written: Callable[[TokenInfo], None] | None = None,
    ) -> tuple[Artifact | None, int]:
        """Write tokens to sink with artifact recording and failsink routing.

        CRITICAL: Creates a node_state for EACH token written AND records
        token outcomes. Node_states are opened BEFORE I/O so that Phase 1
        failures result in FAILED states (not silent drops). States are
        completed as COMPLETED only after sink.flush() confirms durability.

        This is the ONLY place terminal outcomes should be recorded for sink-bound
        tokens. Recording here (not in the orchestrator processing loop) ensures the
        token outcome contract is honored:
        - Invariant 3: "COMPLETED/ROUTED implies the token has a completed sink node_state"
        - Invariant 4: "Completed sink node_state implies a terminal token_outcome"

        Four-phase flow:
        - Pre-phase: Open node_states for ALL tokens at primary sink
        - Phase 1: Call sink.write() → discover diversions (FAILED on error)
        - Phase 2: Complete states for primary (non-diverted) tokens
        - Phase 3: Handle diversions (failsink write or discard)

        Args:
            sink: Sink plugin to write to
            tokens: Tokens to write (may be empty)
            ctx: Plugin context
            step_in_pipeline: Current position in DAG (Orchestrator is authority)
            sink_name: Name of the sink (for token_outcome recording)
            pending_outcome: PendingOutcome containing outcome and optional error_hash.
                    Required - all sink-bound tokens must have their outcome recorded.
            failsink: Resolved failsink instance (or None for discard mode)
            failsink_name: Config-level name of the failsink (for outcome recording)
            failsink_edge_id: Edge ID of the __failsink__ DIVERT edge in the DAG
            on_token_written: Optional callback called for each token after its
                             path completes durably. Primary tokens are checkpointed
                             after Phase 2, diverted tokens after Phase 3.

        Returns:
            Tuple of (Artifact if tokens were written else None, diversion count)

        Raises:
            Exception: Propagated from sink.write(), sink.flush(), or failsink.write()
        """
        if not tokens:
            return None, 0

        # pending_outcome is required for all sink-bound tokens.
        # PendingTokenMap allows None in its type alias, but _route_to_sink()
        # always wraps in PendingOutcome. None here means a routing bug.
        if pending_outcome is None:
            raise OrchestrationInvariantError(
                f"Sink '{sink_name}' received pending_outcome=None — all sink-bound tokens must have a PendingOutcome."
            )

        # Extract dicts from PipelineRow for sink write
        rows = [t.row_data.to_dict() for t in tokens]

        # Sink must have node_id assigned by orchestrator before execution
        if sink.node_id is None:
            raise OrchestrationInvariantError(f"Sink '{sink.name}' executed without node_id - orchestrator bug")
        sink_node_id: str = sink.node_id

        # Synchronize context contract to the sink-bound tokens.
        contract_merge_start = time.perf_counter()
        try:
            batch_contract = tokens[0].row_data.contract
            for token in tokens[1:]:
                batch_contract = batch_contract.merge(token.row_data.contract)
        except TIER_1_ERRORS:
            raise
        except Exception as e:
            merge_duration_ms = (time.perf_counter() - contract_merge_start) * 1000
            raise FrameworkBugError(f"Contract merge failed after {merge_duration_ms:.1f}ms: {e}") from e
        ctx.contract = batch_contract

        # CRITICAL: Clear state_id before entering operation context.
        ctx.state_id = None

        # ── PRE-PHASE: Open node_states for ALL tokens at primary sink ──
        # Opened BEFORE I/O so that Phase 1 failures can record FAILED states,
        # preserving the invariant that every token reaches a terminal state.
        # We don't yet know which tokens will be diverted — that's discovered
        # by sink.write() — so we open states for ALL tokens and partition later.
        all_states: list[tuple[TokenInfo, NodeStateOpen]] = []
        try:
            for token in tokens:
                input_dict = token.row_data.to_dict()
                state = self._execution.begin_node_state(
                    token_id=token.token_id,
                    node_id=sink_node_id,
                    run_id=ctx.run_id,
                    step_index=step_in_pipeline,
                    input_data=input_dict,
                )
                all_states.append((token, state))
        except TIER_1_ERRORS as e:
            if all_states:
                self._best_effort_cleanup(all_states, e, "begin_node_state")
            raise
        except Exception as e:
            if all_states:
                begin_error = ExecutionError(
                    exception=str(e),
                    exception_type=type(e).__name__,
                    phase="begin_node_state",
                )
                try:
                    self._complete_states_failed(
                        states=all_states,
                        duration_ms=0.0,
                        error=begin_error,
                    )
                except TIER_1_ERRORS:
                    raise  # Audit corruption during cleanup is higher priority than original error
                except Exception as cleanup_exc:
                    logger.warning(
                        "Cleanup of %d OPEN states also failed — original error preserved. Cleanup error: %s: %s",
                        len(all_states),
                        type(cleanup_exc).__name__,
                        cleanup_exc,
                    )
            raise

        # Index by token_id for O(1) lookup in Phases 2 and 3.
        state_by_token_id: dict[str, NodeStateOpen] = {token.token_id: state for token, state in all_states}

        # ── PHASE 1: External I/O (inside track_operation) ──
        # If any operation here raises, complete ALL pre-opened states as FAILED
        # before re-raising — no token may exit this method without a terminal state.
        try:
            with track_operation(
                recorder=self._execution,
                run_id=self._run_id,
                node_id=sink_node_id,
                operation_type="sink_write",
                ctx=ctx,
                input_data={"sink_plugin": sink.name, "row_count": len(tokens)},
            ) as handle:
                sink_token_ids = [t.token_id for t in tokens]
                with self._spans.sink_span(
                    sink.name,
                    node_id=sink_node_id,
                    token_ids=sink_token_ids,
                ):
                    # Centralized input validation (before sink.write).
                    # Wrong types at a sink boundary are upstream plugin bugs (Tier 2).
                    # Pass per-row contracts for context-aware error messages.
                    row_contracts = [t.row_data.contract for t in tokens]
                    self._validate_sink_input(sink, rows, contracts=row_contracts)

                    # Reset diversion log and call sink.write()
                    sink._reset_diversion_log()
                    start = time.perf_counter()
                    write_result = sink.write(rows, ctx)
                    if not isinstance(write_result, SinkWriteResult):
                        raise PluginContractViolation(
                            f"Sink '{sink.name}' returned {type(write_result).__name__}, "
                            f"expected SinkWriteResult. This is a sink plugin bug."
                        )
                    artifact_info = write_result.artifact
                    if not isinstance(artifact_info, ArtifactDescriptor):
                        raise PluginContractViolation(
                            f"Sink '{sink.name}' returned SinkWriteResult with artifact of type "
                            f"{type(artifact_info).__name__}, expected ArtifactDescriptor. "
                            f"This is a sink plugin bug."
                        )
                    diversions = write_result.diversions
                    duration_ms = (time.perf_counter() - start) * 1000

                    # Validate diversion indices against the batch we passed in.
                    # SinkWriteResult.__post_init__ already rejects duplicates;
                    # here we check range (only the executor knows the batch size).
                    batch_size = len(tokens)
                    for d in diversions:
                        if d.row_index >= batch_size:
                            raise PluginContractViolation(
                                f"Sink '{sink.name}' returned diversion with row_index={d.row_index} "
                                f"but batch has only {batch_size} rows (valid range: 0..{batch_size - 1}). "
                                f"This is a sink plugin bug."
                            )

                # Flush primary sink for durability
                sink.flush()

                # Set output data on operation handle for audit trail
                handle.output_data = {
                    "artifact_path": artifact_info.path_or_uri,
                    "content_hash": artifact_info.content_hash,
                }
        except TIER_1_ERRORS as e:
            self._best_effort_cleanup(all_states, e, "sink_write")
            raise
        except Exception as e:
            io_error = ExecutionError(
                exception=str(e),
                exception_type=type(e).__name__,
                phase="sink_write",
            )
            self._complete_states_failed(
                states=all_states,
                duration_ms=0.0,
                error=io_error,
            )
            raise

        # ── PHASE 2: Partition and complete primary tokens ──
        diverted_indices = {d.row_index for d in diversions}
        primary_tokens = [(token, i) for i, token in enumerate(tokens) if i not in diverted_indices]
        diverted_tokens = [(token, i) for i, token in enumerate(tokens) if i in diverted_indices]

        artifact: Artifact | None = None

        if primary_tokens:
            # Retrieve pre-opened states for primary tokens.
            primary_states: list[tuple[TokenInfo, NodeStateOpen]] = [
                (token, state_by_token_id[token.token_id]) for token, _ in primary_tokens
            ]

            # Amortize batch write time across ALL tokens (including diverted)
            # since sink.write() processed the entire batch
            per_token_ms = duration_ms / len(tokens)
            for token, state in primary_states:
                output_dict = token.row_data.to_dict()
                sink_output = {
                    "row": output_dict,
                    "artifact_path": artifact_info.path_or_uri,
                    "content_hash": artifact_info.content_hash,
                }
                self._execution.complete_node_state(
                    state_id=state.state_id,
                    status=NodeStateStatus.COMPLETED,
                    output_data=sink_output,
                    duration_ms=per_token_ms,
                )

            # Register artifact (linked to first primary state)
            first_state = primary_states[0][1]
            artifact = self._execution.register_artifact(
                run_id=self._run_id,
                state_id=first_state.state_id,
                sink_node_id=sink_node_id,
                artifact_type=artifact_info.artifact_type,
                path=artifact_info.path_or_uri,
                content_hash=artifact_info.content_hash,
                size_bytes=artifact_info.size_bytes,
            )

            # Record COMPLETED outcomes for primary tokens
            for token, _ in primary_states:
                self._data_flow.record_token_outcome(
                    ref=TokenRef(token_id=token.token_id, run_id=self._run_id),
                    outcome=pending_outcome.outcome,
                    error_hash=pending_outcome.error_hash,
                    sink_name=sink_name,
                )

            # Checkpoint callback — only for primary tokens.
            # Failures crash with AuditIntegrityError: the sink write is durable
            # but the checkpoint record is missing, leaving the audit trail
            # inconsistent. Logging-and-continuing would silently cause duplicate
            # writes on resume — a worse outcome than crashing.
            if on_token_written is not None:
                for token, _ in primary_tokens:
                    try:
                        on_token_written(token)
                    except TIER_1_ERRORS:
                        raise
                    except Exception as exc:
                        raise AuditIntegrityError(
                            f"Checkpoint failed after durable sink write for token {token.token_id}. "
                            f"Sink artifact exists but no checkpoint record created — "
                            f"audit trail is inconsistent. "
                            f"Original error: {type(exc).__name__}: {exc}"
                        ) from exc

        # ── PHASE 3: Handle diversions ──
        # Diverted tokens already have node_states at the PRIMARY sink from
        # the pre-phase. These are the routing anchors — routing_event.state_id
        # points here. Failsink-mode tokens ALSO get a NEW state at the
        # failsink node (the destination).
        diversion_count = len(diverted_tokens)
        if diverted_tokens:
            diversion_by_index = {d.row_index: d for d in diversions}

            # Retrieve pre-opened states for diverted tokens.
            primary_divert_states: list[tuple[TokenInfo, int, NodeStateOpen]] = [
                (token, idx, state_by_token_id[token.token_id]) for token, idx in diverted_tokens
            ]

            if failsink is not None:
                # Failsink mode: write enriched rows to failsink
                if failsink.node_id is None:
                    raise OrchestrationInvariantError(f"Failsink '{failsink.name}' executed without node_id - orchestrator bug")
                if failsink_edge_id is None:
                    raise OrchestrationInvariantError("failsink_edge_id is None but failsink is not None — orchestrator bug")
                if failsink_name is None:
                    raise OrchestrationInvariantError("failsink_name is None but failsink is not None — orchestrator bug")
                failsink_node_id: str = failsink.node_id

                # Build enriched rows — keyed by token_id so failsink node states
                # can record the enriched payload (what was actually written), not
                # the original row data.
                iso_ts = datetime.now(UTC).isoformat()
                enriched_rows: list[dict[str, object]] = []
                enriched_by_token: dict[str, dict[str, object]] = {}
                for token, idx, _state in primary_divert_states:
                    diversion = diversion_by_index[idx]
                    enriched_row = {
                        **diversion.row_data,
                        "__diversion_reason": diversion.reason,
                        "__diverted_from": sink_name,
                        "__diversion_timestamp": iso_ts,
                    }
                    enriched_rows.append(enriched_row)
                    enriched_by_token[token.token_id] = enriched_row

                # Write to failsink — if validation or write fails, complete
                # primary divert states as FAILED before re-raising (they're
                # already open from the pre-phase).
                failsink._reset_diversion_log()
                try:
                    # Validate enriched rows against failsink required fields.
                    # skip_schema=True because the executor injects __diversion_*
                    # fields that are outside the failsink's declared schema —
                    # a fixed-schema failsink (extra="forbid") would reject them.
                    # Required-field checking still catches missing upstream fields.
                    # Inside the try block so failures close primary divert states.
                    failsink_contracts = [t.row_data.contract for t, _, _ in primary_divert_states]
                    self._validate_sink_input(failsink, enriched_rows, skip_schema=True, contracts=failsink_contracts)
                    failsink_write_result = failsink.write(enriched_rows, ctx)
                    failsink.flush()
                except TIER_1_ERRORS:
                    raise
                except Exception as e:
                    fs_write_error = ExecutionError(
                        exception=str(e),
                        exception_type=type(e).__name__,
                        phase="failsink_write",
                    )
                    self._complete_states_failed(
                        states=[(t, s) for t, _, s in primary_divert_states],
                        duration_ms=0.0,
                        error=fs_write_error,
                    )
                    raise

                if failsink_write_result.diversions:
                    raise FrameworkBugError(
                        f"Failsink '{failsink_name}' produced {len(failsink_write_result.diversions)} "
                        f"diversions during failsink write — failsinks must not divert rows."
                    )

                failsink_artifact_info = failsink_write_result.artifact
                if not isinstance(failsink_artifact_info, ArtifactDescriptor):
                    raise PluginContractViolation(
                        f"Failsink '{failsink_name}' returned SinkWriteResult with artifact of type "
                        f"{type(failsink_artifact_info).__name__}, expected ArtifactDescriptor. "
                        f"This is a sink plugin bug."
                    )

                # Open node_states at failsink node (destination).
                # Use the enriched payload (what was actually written to the failsink),
                # not the original row data — the audit trail must reflect the persisted data.
                failsink_states: list[tuple[TokenInfo, NodeStateOpen]] = []
                try:
                    for token, _idx, _primary_state in primary_divert_states:
                        input_dict = enriched_by_token[token.token_id]
                        state = self._execution.begin_node_state(
                            token_id=token.token_id,
                            node_id=failsink_node_id,
                            run_id=ctx.run_id,
                            step_index=step_in_pipeline,
                            input_data=input_dict,
                        )
                        failsink_states.append((token, state))
                except TIER_1_ERRORS as e:
                    # Best-effort: close partially-opened failsink states + primary divert states
                    all_open = failsink_states + [(t, s) for t, _, s in primary_divert_states]
                    if all_open:
                        self._best_effort_cleanup(all_open, e, "begin_node_state_failsink")
                    raise
                except Exception as e:
                    begin_error = ExecutionError(
                        exception=str(e),
                        exception_type=type(e).__name__,
                        phase="begin_node_state_failsink",
                    )
                    # Close any partially-opened failsink states
                    if failsink_states:
                        self._complete_states_failed(
                            states=failsink_states,
                            duration_ms=0.0,
                            error=begin_error,
                        )
                    # Also close the already-open primary divert states —
                    # they were opened before the failsink write and are still OPEN.
                    self._complete_states_failed(
                        states=[(t, s) for t, _, s in primary_divert_states],
                        duration_ms=0.0,
                        error=begin_error,
                    )
                    raise

                # Record routing_event anchored to PRIMARY sink state (the routing node),
                # complete primary state as FAILED, then complete failsink state.
                # This matches the quarantine pattern: routing_event lives at the
                # node that made the routing decision.
                #
                # Wrapped in try/except to clean up any remaining OPEN states
                # if a recorder call fails mid-loop (F3 fix from review).
                completed_primary_indices: set[int] = set()
                completed_failsink_indices: set[int] = set()
                try:
                    for loop_idx, ((token, idx, primary_state), (_, fs_state)) in enumerate(
                        zip(primary_divert_states, failsink_states, strict=True)
                    ):
                        diversion = diversion_by_index[idx]
                        reason: SinkDiversionReason = {"diversion_reason": diversion.reason}

                        # Routing event anchored to primary sink state
                        self._execution.record_routing_event(
                            state_id=primary_state.state_id,
                            edge_id=failsink_edge_id,
                            mode=RoutingMode.DIVERT,
                            reason=reason,
                        )

                        # Complete primary state as FAILED — the row didn't get where
                        # it was going. FAILED is a row state, not a system state:
                        # the pipeline is healthy, the row failed at this stop.
                        # Matches the quarantine pattern (core.py:1835).
                        divert_error = ExecutionError(
                            exception=diversion.reason,
                            exception_type="SinkDiversion",
                            phase="write",
                        )
                        self._execution.complete_node_state(
                            state_id=primary_state.state_id,
                            status=NodeStateStatus.FAILED,
                            output_data={"diverted_to": failsink_name, "reason": diversion.reason},
                            duration_ms=0.0,
                            error=divert_error,
                        )
                        completed_primary_indices.add(loop_idx)

                        # Complete failsink state (token written to failsink).
                        # Use enriched row — that's what was actually persisted.
                        failsink_output = {
                            "row": enriched_by_token[token.token_id],
                            "artifact_path": failsink_artifact_info.path_or_uri,
                            "content_hash": failsink_artifact_info.content_hash,
                        }
                        self._execution.complete_node_state(
                            state_id=fs_state.state_id,
                            status=NodeStateStatus.COMPLETED,
                            output_data=failsink_output,
                            duration_ms=0.0,
                        )
                        completed_failsink_indices.add(loop_idx)
                except TIER_1_ERRORS as e:
                    # Best-effort: close remaining OPEN states before crash.
                    remaining = [(t, s) for i, (t, _, s) in enumerate(primary_divert_states) if i not in completed_primary_indices] + [
                        (t, s) for i, (t, s) in enumerate(failsink_states) if i not in completed_failsink_indices
                    ]
                    if remaining:
                        self._best_effort_cleanup(remaining, e, "failsink_audit_recording")
                    raise
                except Exception as e:
                    # Close any remaining OPEN states from tokens not yet processed.
                    loop_error = ExecutionError(
                        exception=str(e),
                        exception_type=type(e).__name__,
                        phase="failsink_audit_recording",
                    )
                    remaining_primary = [(t, s) for i, (t, _, s) in enumerate(primary_divert_states) if i not in completed_primary_indices]
                    remaining_failsink = [(t, s) for i, (t, s) in enumerate(failsink_states) if i not in completed_failsink_indices]
                    if remaining_primary:
                        self._complete_states_failed(
                            states=remaining_primary,
                            duration_ms=0.0,
                            error=loop_error,
                        )
                    if remaining_failsink:
                        self._complete_states_failed(
                            states=remaining_failsink,
                            duration_ms=0.0,
                            error=loop_error,
                        )
                    raise

                # Register failsink artifact
                first_fs_state = failsink_states[0][1]
                self._execution.register_artifact(
                    run_id=self._run_id,
                    state_id=first_fs_state.state_id,
                    sink_node_id=failsink_node_id,
                    artifact_type=failsink_artifact_info.artifact_type,
                    path=failsink_artifact_info.path_or_uri,
                    content_hash=failsink_artifact_info.content_hash,
                    size_bytes=failsink_artifact_info.size_bytes,
                )

                # Record DIVERTED outcomes
                for token, idx, _primary_state in primary_divert_states:
                    diversion = diversion_by_index[idx]
                    error_hash = hashlib.sha256(diversion.reason.encode()).hexdigest()[:16]
                    self._data_flow.record_token_outcome(
                        ref=TokenRef(token_id=token.token_id, run_id=self._run_id),
                        outcome=RowOutcome.DIVERTED,
                        error_hash=error_hash,
                        sink_name=failsink_name,
                    )

                # Checkpoint diverted tokens — failsink write is now durable.
                # Without this, a crash after failsink write but before the next
                # primary checkpoint leaves diverted tokens uncheckpointed,
                # causing duplicate failsink writes on resume.
                if on_token_written is not None:
                    for token, _idx, _state in primary_divert_states:
                        try:
                            on_token_written(token)
                        except TIER_1_ERRORS:
                            raise
                        except Exception as exc:
                            raise AuditIntegrityError(
                                f"Checkpoint failed after durable failsink write for diverted token {token.token_id}. "
                                f"Failsink artifact exists but no checkpoint record created — "
                                f"audit trail is inconsistent. "
                                f"Original error: {type(exc).__name__}: {exc}"
                            ) from exc

            else:
                # Discard mode: complete primary states and record DIVERTED outcomes.
                # No routing_event (no DAG edge for discard), no failsink write.
                for token, idx, primary_state in primary_divert_states:
                    diversion = diversion_by_index[idx]

                    # FAILED — the row didn't reach its destination (discarded).
                    discard_error = ExecutionError(
                        exception=diversion.reason,
                        exception_type="SinkDiscard",
                        phase="write",
                    )
                    self._execution.complete_node_state(
                        state_id=primary_state.state_id,
                        status=NodeStateStatus.FAILED,
                        output_data={"discarded": True, "reason": diversion.reason},
                        duration_ms=0.0,
                        error=discard_error,
                    )

                    error_hash = hashlib.sha256(diversion.reason.encode()).hexdigest()[:16]
                    self._data_flow.record_token_outcome(
                        ref=TokenRef(token_id=token.token_id, run_id=self._run_id),
                        outcome=RowOutcome.DIVERTED,
                        error_hash=error_hash,
                        sink_name="__discard__",
                    )

                # Checkpoint diverted tokens — discard recording is now durable.
                # Discard is idempotent, but checkpointing keeps resume state consistent.
                if on_token_written is not None:
                    for token, _idx, _state in primary_divert_states:
                        try:
                            on_token_written(token)
                        except TIER_1_ERRORS:
                            raise
                        except Exception as exc:
                            raise AuditIntegrityError(
                                f"Checkpoint failed after discard recording for diverted token {token.token_id}. "
                                f"Original error: {type(exc).__name__}: {exc}"
                            ) from exc

        return artifact, diversion_count
