"""SinkExecutor - wraps sink.write() with artifact recording."""

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from elspeth.contracts import (
    Artifact,
    ExecutionError,
    NodeStateOpen,
    PendingOutcome,
    RowOutcome,
    SinkProtocol,
    TokenInfo,
)
from elspeth.contracts.diversion import SinkWriteResult
from elspeth.contracts.enums import NodeStateStatus, RoutingMode
from elspeth.contracts.errors import (
    AuditIntegrityError,
    FrameworkBugError,
    OrchestrationInvariantError,
    PluginContractViolation,
    SinkDiversionReason,
)
from elspeth.contracts.plugin_context import PluginContext
from elspeth.core.landscape import LandscapeRecorder
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

    CRITICAL: Every token reaching a sink gets a node_state — at the primary
    sink for accepted rows, or at the failsink for diverted rows. Discard-mode
    tokens get a DIVERTED outcome but no node_state (audit trade-off documented
    in spec).

    Note: Unlike TransformExecutor/GateExecutor/AggregationExecutor, SinkExecutor
    does NOT use StepResolver. Sinks are not DAG processing nodes — their step is
    always max(processing_steps) + 1, computed by RowProcessor.resolve_sink_step()
    and passed as step_in_pipeline by the orchestrator. This is intentional: sinks
    exist after all processing nodes and have a fixed, deterministic step position.

    Example:
        executor = SinkExecutor(recorder, span_factory, run_id)
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
        recorder: LandscapeRecorder,
        span_factory: SpanFactory,
        run_id: str,
    ) -> None:
        """Initialize executor.

        Args:
            recorder: Landscape recorder for audit trail
            span_factory: Span factory for tracing
            run_id: Run identifier for artifact registration
        """
        self._recorder = recorder
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
        per_token_ms = duration_ms / len(states)
        for _, state in states:
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=per_token_ms,
                error=error,
            )

    def write(
        self,
        sink: SinkProtocol,
        tokens: list[TokenInfo],
        ctx: PluginContext,
        step_in_pipeline: int,
        *,
        sink_name: str,
        pending_outcome: PendingOutcome,
        failsink: SinkProtocol | None = None,
        failsink_name: str | None = None,
        failsink_edge_id: str | None = None,
        on_token_written: Callable[[TokenInfo], None] | None = None,
    ) -> tuple[Artifact | None, int]:
        """Write tokens to sink with artifact recording and failsink routing.

        CRITICAL: Creates a node_state for EACH token written AND records
        token outcomes. Both records are created AFTER sink.flush()
        to ensure they only exist when data is durably written.

        This is the ONLY place terminal outcomes should be recorded for sink-bound
        tokens. Recording here (not in the orchestrator processing loop) ensures the
        token outcome contract is honored:
        - Invariant 3: "COMPLETED/ROUTED implies the token has a completed sink node_state"
        - Invariant 4: "Completed sink node_state implies a terminal token_outcome"

        Three-phase flow:
        - Phase 1: Call sink.write() → discover diversions
        - Phase 2: Open/complete states for primary (non-diverted) tokens
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
            on_token_written: Optional callback called for each PRIMARY token after
                             successful write. NOT called for diverted tokens.

        Returns:
            Tuple of (Artifact if tokens were written else None, diversion count)

        Raises:
            Exception: Propagated from sink.write(), sink.flush(), or failsink.write()
        """
        if not tokens:
            return None, 0

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
        except (FrameworkBugError, AuditIntegrityError):
            raise
        except Exception as e:
            merge_duration_ms = (time.perf_counter() - contract_merge_start) * 1000
            raise FrameworkBugError(f"Contract merge failed after {merge_duration_ms:.1f}ms: {e}") from e
        ctx.contract = batch_contract

        # CRITICAL: Clear state_id before entering operation context.
        ctx.state_id = None

        # ── PHASE 1: External I/O (inside track_operation) ──
        with track_operation(
            recorder=self._recorder,
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
                # Centralized input validation (before sink.write)
                try:
                    if sink.validate_input:
                        from pydantic import ValidationError

                        for row in rows:
                            try:
                                sink.input_schema.model_validate(row)
                            except ValidationError as e:
                                raise PluginContractViolation(
                                    f"Sink '{sink.name}' input validation failed: {e}. "
                                    f"This indicates an upstream transform/source schema bug."
                                ) from e

                    if sink.declared_required_fields:
                        for row_index, row in enumerate(rows):
                            missing = sorted(f for f in sink.declared_required_fields if f not in row)
                            if missing:
                                raise PluginContractViolation(
                                    f"Sink '{sink.name}' row {row_index} is missing required fields "
                                    f"{missing}. This indicates an upstream transform/schema bug."
                                )
                except (FrameworkBugError, AuditIntegrityError):
                    raise
                except Exception:
                    raise

                # Reset diversion log and call sink.write()
                sink._reset_diversion_log()
                start = time.perf_counter()
                try:
                    write_result: SinkWriteResult = sink.write(rows, ctx)
                    artifact_info = write_result.artifact
                    diversions = write_result.diversions
                    duration_ms = (time.perf_counter() - start) * 1000
                except (FrameworkBugError, AuditIntegrityError):
                    raise
                except Exception:
                    raise

            # Flush primary sink for durability
            try:
                sink.flush()
            except (FrameworkBugError, AuditIntegrityError):
                raise
            except Exception:
                raise

            # Set output data on operation handle for audit trail
            handle.output_data = {
                "artifact_path": artifact_info.path_or_uri,
                "content_hash": artifact_info.content_hash,
            }

        # ── PHASE 2: Partition and record primary tokens ──
        diverted_indices = {d.row_index for d in diversions}
        primary_tokens = [(token, i) for i, token in enumerate(tokens) if i not in diverted_indices]
        diverted_tokens = [(token, i) for i, token in enumerate(tokens) if i in diverted_indices]

        artifact: Artifact | None = None

        if primary_tokens:
            # Open and complete node_states for primary tokens
            primary_states: list[tuple[TokenInfo, NodeStateOpen]] = []
            try:
                for token, _ in primary_tokens:
                    input_dict = token.row_data.to_dict()
                    state = self._recorder.begin_node_state(
                        token_id=token.token_id,
                        node_id=sink_node_id,
                        run_id=ctx.run_id,
                        step_index=step_in_pipeline,
                        input_data=input_dict,
                    )
                    primary_states.append((token, state))
            except (FrameworkBugError, AuditIntegrityError):
                raise
            except Exception as e:
                if primary_states:
                    begin_error = ExecutionError(
                        exception=str(e),
                        exception_type=type(e).__name__,
                        phase="begin_node_state",
                    )
                    self._complete_states_failed(
                        states=primary_states,
                        duration_ms=0.0,
                        error=begin_error,
                    )
                raise

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
                self._recorder.complete_node_state(
                    state_id=state.state_id,
                    status=NodeStateStatus.COMPLETED,
                    output_data=sink_output,
                    duration_ms=per_token_ms,
                )

            # Register artifact (linked to first primary state)
            first_state = primary_states[0][1]
            artifact = self._recorder.register_artifact(
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
                self._recorder.record_token_outcome(
                    run_id=self._run_id,
                    token_id=token.token_id,
                    outcome=pending_outcome.outcome,
                    error_hash=pending_outcome.error_hash,
                    sink_name=sink_name,
                )

            # Checkpoint callback — only for primary tokens
            if on_token_written is not None:
                for token, _ in primary_tokens:
                    try:
                        on_token_written(token)
                    except (FrameworkBugError, AuditIntegrityError):
                        raise
                    except Exception as e:
                        logger.error(
                            "Checkpoint failed after durable sink write for token %s. "
                            "Sink artifact exists but no checkpoint record created. "
                            "Resume will replay this row (duplicate write). "
                            "Manual cleanup may be required. Error: %s",
                            token.token_id,
                            e,
                            exc_info=True,
                        )

        # ── PHASE 3: Handle diversions ──
        diversion_count = len(diverted_tokens)
        if diverted_tokens:
            # Build diversion lookup by row_index
            diversion_by_index = {d.row_index: d for d in diversions}

            on_write_failure = sink._on_write_failure

            if on_write_failure != "discard" and failsink is not None:
                # Failsink mode: write enriched rows to failsink
                if failsink.node_id is None:
                    raise OrchestrationInvariantError(f"Failsink '{failsink.name}' executed without node_id - orchestrator bug")
                failsink_node_id: str = failsink.node_id

                # Build enriched rows
                iso_ts = datetime.now(UTC).isoformat()
                enriched_rows = []
                for _token, idx in diverted_tokens:
                    diversion = diversion_by_index[idx]
                    enriched_row = {
                        **diversion.row_data,
                        "__diversion_reason": diversion.reason,
                        "__diverted_from": sink_name,
                        "__diversion_timestamp": iso_ts,
                    }
                    enriched_rows.append(enriched_row)

                # Write to failsink
                failsink._reset_diversion_log()
                try:
                    failsink_write_result = failsink.write(enriched_rows, ctx)
                    failsink.flush()
                except (FrameworkBugError, AuditIntegrityError):
                    raise
                except Exception:
                    raise

                failsink_artifact_info = failsink_write_result.artifact

                # Open and complete node_states at failsink node
                failsink_states: list[tuple[TokenInfo, NodeStateOpen]] = []
                try:
                    for token, _idx in diverted_tokens:
                        input_dict = token.row_data.to_dict()
                        state = self._recorder.begin_node_state(
                            token_id=token.token_id,
                            node_id=failsink_node_id,
                            run_id=ctx.run_id,
                            step_index=step_in_pipeline,
                            input_data=input_dict,
                        )
                        failsink_states.append((token, state))
                except (FrameworkBugError, AuditIntegrityError):
                    raise
                except Exception as e:
                    if failsink_states:
                        begin_error = ExecutionError(
                            exception=str(e),
                            exception_type=type(e).__name__,
                            phase="begin_node_state_failsink",
                        )
                        self._complete_states_failed(
                            states=failsink_states,
                            duration_ms=0.0,
                            error=begin_error,
                        )
                    raise

                # Record routing_event and complete failsink states
                # failsink_edge_id is guaranteed non-None when failsink is not None
                # (validated in orchestrator's failsink resolution)
                if failsink_edge_id is None:
                    raise OrchestrationInvariantError("failsink_edge_id is None but failsink is not None — orchestrator bug")
                if failsink_name is None:
                    raise OrchestrationInvariantError("failsink_name is None but failsink is not None — orchestrator bug")
                for (token, idx), (_, fs_state) in zip(diverted_tokens, failsink_states, strict=True):
                    diversion = diversion_by_index[idx]

                    # Routing event links primary sink → failsink
                    reason: SinkDiversionReason = {"diversion_reason": diversion.reason}
                    self._recorder.record_routing_event(
                        state_id=fs_state.state_id,
                        edge_id=failsink_edge_id,
                        mode=RoutingMode.DIVERT,
                        reason=reason,
                    )

                    output_dict = token.row_data.to_dict()
                    failsink_output = {
                        "row": output_dict,
                        "artifact_path": failsink_artifact_info.path_or_uri,
                        "content_hash": failsink_artifact_info.content_hash,
                    }
                    self._recorder.complete_node_state(
                        state_id=fs_state.state_id,
                        status=NodeStateStatus.COMPLETED,
                        output_data=failsink_output,
                        duration_ms=0.0,
                    )

                # Register failsink artifact
                first_fs_state = failsink_states[0][1]
                self._recorder.register_artifact(
                    run_id=self._run_id,
                    state_id=first_fs_state.state_id,
                    sink_node_id=failsink_node_id,
                    artifact_type=failsink_artifact_info.artifact_type,
                    path=failsink_artifact_info.path_or_uri,
                    content_hash=failsink_artifact_info.content_hash,
                    size_bytes=failsink_artifact_info.size_bytes,
                )

                # Record DIVERTED outcomes with failsink name
                for token, idx in diverted_tokens:
                    diversion = diversion_by_index[idx]
                    error_hash = hashlib.sha256(diversion.reason.encode()).hexdigest()[:16]
                    self._recorder.record_token_outcome(
                        run_id=self._run_id,
                        token_id=token.token_id,
                        outcome=RowOutcome.DIVERTED,
                        error_hash=error_hash,
                        sink_name=failsink_name,
                    )

            else:
                # Discard mode: record DIVERTED outcomes only (no routing_event, no failsink write)
                for token, idx in diverted_tokens:
                    diversion = diversion_by_index[idx]
                    error_hash = hashlib.sha256(diversion.reason.encode()).hexdigest()[:16]
                    self._recorder.record_token_outcome(
                        run_id=self._run_id,
                        token_id=token.token_id,
                        outcome=RowOutcome.DIVERTED,
                        error_hash=error_hash,
                        sink_name="__discard__",
                    )

        return artifact, diversion_count
