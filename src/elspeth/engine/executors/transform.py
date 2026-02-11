# src/elspeth/engine/executors/transform.py
"""TransformExecutor - wraps transform.process() with audit recording."""

import logging
import time
from typing import TYPE_CHECKING, Any, cast

import structlog

from elspeth.contracts import (
    ExecutionError,
    TokenInfo,
)
from elspeth.contracts.enums import (
    NodeStateStatus,
    RoutingMode,
)
from elspeth.contracts.errors import OrchestrationInvariantError, PluginContractViolation
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.types import NodeID, StepResolver
from elspeth.core.canonical import stable_hash
from elspeth.core.landscape import LandscapeRecorder
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.batching.mixin import BatchTransformMixin
from elspeth.plugins.protocols import TransformProtocol
from elspeth.plugins.results import TransformResult

if TYPE_CHECKING:
    from elspeth.engine.batch_adapter import SharedBatchAdapter

logger = logging.getLogger(__name__)
slog = structlog.get_logger(__name__)


class TransformExecutor:
    """Executes transforms with audit recording.

    Wraps transform.process() to:
    1. Record node state start
    2. Time the operation
    3. Populate audit fields in result
    4. Record node state completion
    5. Emit OpenTelemetry span

    Example:
        executor = TransformExecutor(recorder, span_factory, step_resolver)
        result, updated_token, error_sink = executor.execute_transform(
            transform=my_transform,
            token=token,
            ctx=ctx,
        )
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        span_factory: SpanFactory,
        step_resolver: StepResolver,
        max_workers: int | None = None,
        error_edge_ids: dict[NodeID, str] | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            recorder: Landscape recorder for audit trail
            span_factory: Span factory for tracing
            step_resolver: Resolves NodeID to 1-indexed audit step position
            max_workers: Maximum concurrent workers (None = no limit)
            error_edge_ids: Map of transform node_id -> DIVERT edge_id for error routing.
                           Built by the processor from the edge_map using error_edge_label().
                           Only populated for transforms with on_error pointing to a real sink.
        """
        self._recorder = recorder
        self._spans = span_factory
        self._step_resolver = step_resolver
        self._max_workers = max_workers
        self._error_edge_ids = error_edge_ids or {}
        # Adapter storage keyed by node_id — one SharedBatchAdapter per
        # mixin-based transform, owned by the executor (not monkey-patched
        # onto the transform instance).
        self._batch_adapters: dict[str, "SharedBatchAdapter"] = {}  # noqa: UP037 — forward ref, no __future__ annotations

    def _get_batch_adapter(self, transform: TransformProtocol) -> "SharedBatchAdapter":
        """Get or create shared batch adapter for a mixin-based transform.

        Creates adapter once per transform and stores it in the executor's
        own dict (keyed by node_id). On first call, connects the adapter as
        the transform's output port.

        Caller must verify isinstance(transform, BatchTransformMixin) before
        calling — this method accesses mixin attributes directly.

        Args:
            transform: Transform using BatchTransformMixin (must have node_id set)

        Returns:
            SharedBatchAdapter for this transform
        """
        from elspeth.engine.batch_adapter import SharedBatchAdapter

        # node_id is always set by orchestrator before execution
        node_id = transform.node_id
        assert node_id is not None, "node_id must be set before execute_transform"

        if node_id not in self._batch_adapters:
            adapter = SharedBatchAdapter()
            self._batch_adapters[node_id] = adapter

            # Connect output (one-time setup)
            # Cap pool_size to max_workers if configured (global concurrency limit)
            # Safe: caller guarantees isinstance(transform, BatchTransformMixin)
            mixin = cast(BatchTransformMixin, transform)
            max_pending = mixin._pool_size
            if self._max_workers is not None:
                max_pending = min(max_pending, self._max_workers)
            mixin.connect_output(output=adapter, max_pending=max_pending)

        return self._batch_adapters[node_id]

    def execute_transform(
        self,
        transform: TransformProtocol,
        token: TokenInfo,
        ctx: PluginContext,
        attempt: int = 0,
    ) -> tuple[TransformResult, TokenInfo, str | None]:
        """Execute a transform with full audit recording and error routing.

        This method handles a SINGLE ATTEMPT. Retry logic is the caller's
        responsibility (e.g., RetryManager wraps this for retryable transforms).
        Each attempt gets its own node_state record with attempt number tracked
        by the caller.

        Supports two execution modes:
        1. Synchronous: transform.process() returns TransformResult immediately
        2. Asynchronous (BatchTransformMixin): transform.accept() submits work,
           results flow through output port and are awaited synchronously

        Error Routing:
        - TransformResult.error() is a LEGITIMATE processing failure
        - Routes to configured sink via transform.on_error
        - RuntimeError if transform errors without on_error config
        - Exceptions are BUGS and propagate (not routed)

        The step position in the DAG is resolved internally via StepResolver
        using transform.node_id, rather than being passed as a parameter.

        Args:
            transform: Transform plugin to execute
            token: Current token with row data
            ctx: Plugin context
            attempt: Attempt number for retry tracking (0-indexed, default 0)

        Returns:
            Tuple of (TransformResult with audit fields, updated TokenInfo, error_sink)
            where error_sink is:
            - None if transform succeeded
            - "discard" if transform errored and on_error == "discard"
            - The sink name if transform errored and on_error is a sink name

        Raises:
            Exception: Re-raised from transform.process() after recording failure
            RuntimeError: Transform returned error but has no on_error configured
        """
        if transform.node_id is None:
            raise OrchestrationInvariantError(f"Transform '{transform.name}' executed without node_id - orchestrator bug")

        # Resolve step position from node_id (injected StepResolver)
        step = self._step_resolver(NodeID(transform.node_id))

        # Extract dict from PipelineRow for hashing and Landscape recording
        # Landscape stores raw dicts, not PipelineRow objects
        input_dict = token.row_data.to_dict()
        input_hash = stable_hash(input_dict)

        # Begin node state with dict (for Landscape recording)
        state = self._recorder.begin_node_state(
            token_id=token.token_id,
            node_id=transform.node_id,
            run_id=ctx.run_id,
            step_index=step,
            input_data=input_dict,
            attempt=attempt,
        )

        # Set state_id and node_id on context for external call recording
        # and batch checkpoint lookup (node_id required for _batch_checkpoints keying)
        ctx.state_id = state.state_id
        ctx.node_id = transform.node_id
        # Note: call_index allocation is handled by LandscapeRecorder.allocate_call_index()
        # which automatically starts at 0 for each new state_id

        # Set ctx.contract for plugins that use fallback access (dual-name resolution)
        # This allows transforms to access original header names via ctx.contract.resolve_name()
        ctx.contract = token.row_data.contract

        # Detect mixin-based concurrent transforms (accept/connect_output pattern).
        # isinstance is the correct narrowing — these transforms inherit
        # BatchTransformMixin but have is_batch_aware=False (that flag is for
        # aggregation via BatchTransformProtocol, a separate concept).
        mixin: BatchTransformMixin | None = transform if isinstance(transform, BatchTransformMixin) else None

        # Execute with timing and span
        # P2-2026-01-21: Pass token_id for accurate child token attribution in traces
        # P2-2026-01-21: Pass node_id for disambiguation when multiple plugin instances exist
        with self._spans.transform_span(
            transform.name,
            node_id=transform.node_id,
            input_hash=input_hash,
            token_id=token.token_id,
        ):
            start = time.perf_counter()
            try:
                if mixin is not None:
                    # Batch transform: use accept() with SharedBatchAdapter
                    # One adapter per transform, multiple waiters per adapter
                    adapter = self._get_batch_adapter(transform)

                    # Register waiter for THIS token AND attempt (before accept!)
                    # Using (token_id, state_id) ensures retry safety: if a timeout
                    # occurs and retry happens, the new attempt's waiter won't receive
                    # stale results from the previous attempt.
                    waiter = adapter.register(token.token_id, state.state_id)

                    # Set token on context for BatchTransformMixin
                    ctx.token = token

                    # Submit work - this returns immediately
                    mixin.accept(token.row_data, ctx)

                    # Block until THIS row's result arrives.
                    #
                    # DESIGN DECISION: Sequential row processing
                    # The orchestrator processes rows one at a time, blocking here
                    # until each row completes. This is intentional:
                    # - Concurrency happens WITHIN each row (multi-query transforms
                    #   make 10+ LLM calls concurrently for a single row)
                    # - Across rows, processing is sequential for:
                    #   1. Simpler audit ordering (deterministic state progression)
                    #   2. Natural backpressure (no unbounded queue growth)
                    #   3. Single-threaded orchestrator (easier to reason about)
                    #
                    # For true cross-row parallelism, the orchestrator would need
                    # to be async/await or multi-threaded, which adds complexity.
                    #
                    # Timeout is derived from transform's batch_wait_timeout config
                    # (default 3600s = 1 hour) to allow for sustained rate limiting
                    # and AIMD backoff during capacity errors.
                    result = waiter.wait(timeout=mixin._batch_wait_timeout)
                else:
                    # Regular transform: synchronous process()
                    result = transform.process(token.row_data, ctx)

                duration_ms = (time.perf_counter() - start) * 1000
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                # Record failure
                error: ExecutionError = {
                    "exception": str(e),
                    "type": type(e).__name__,
                }
                self._recorder.complete_node_state(
                    state_id=state.state_id,
                    status=NodeStateStatus.FAILED,
                    duration_ms=duration_ms,
                    error=error,
                )

                # For TimeoutError on batch transforms, evict the buffer entry
                # to prevent FIFO blocking on retry attempts.
                #
                # The eviction flow:
                # 1. First attempt times out at waiter.wait()
                # 2. We call evict_submission() to remove buffer entry
                # 3. Retry attempt gets new sequence number and can proceed
                # 4. Original worker may still complete, but result is discarded
                if isinstance(e, TimeoutError) and mixin is not None:
                    try:
                        mixin.evict_submission(token.token_id, state.state_id)
                    except Exception as evict_err:
                        raise RuntimeError(f"Failed to evict timed-out submission for token {token.token_id}") from evict_err

                raise

        # Populate audit fields
        # Wrap stable_hash calls to convert canonicalization errors to PluginContractViolation.
        # stable_hash calls canonical_json which rejects NaN, Infinity, non-serializable types.
        # Per CLAUDE.md: plugin bugs must crash with clear error messages.
        result.input_hash = input_hash
        try:
            if result.row is not None:
                result.output_hash = stable_hash(result.row)
            elif result.rows is not None:
                result.output_hash = stable_hash(result.rows)
            else:
                result.output_hash = None
        except (TypeError, ValueError) as e:
            raise PluginContractViolation(
                f"Transform '{transform.name}' emitted non-canonical data: {e}. "
                f"Ensure output contains only JSON-serializable types. "
                f"Use None instead of NaN for missing values."
            ) from e
        result.duration_ms = duration_ms

        # Initialize error_sink - will be set if transform errors with on_error configured
        error_sink: str | None = None

        # Complete node state
        if result.status == "success":
            # TransformResult.success() or success_multi() always sets output data
            if not result.has_output_data:
                raise RuntimeError(f"Transform '{transform.name}' returned success but has no output data")

            # Extract dicts for audit trail (Tier 1: full trust - store plain dicts)
            # Transforms return PipelineRow — extract underlying dicts for storage
            output_data: dict[str, Any] | list[dict[str, Any]]
            if result.row is not None:
                output_data = result.row.to_dict()
            else:
                assert result.rows is not None, "has_output_data guarantees rows when row is None"
                output_data = [r.to_dict() for r in result.rows]

            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.COMPLETED,
                output_data=output_data,
                duration_ms=duration_ms,
                success_reason=result.success_reason,
                context_after=result.context_after,
            )

            # Record schema evolution if transform adds fields
            # Transforms signal field addition via transforms_adds_fields attribute
            # When True, compute evolved contract and record to audit trail
            if result.row is not None and transform.transforms_adds_fields:
                from elspeth.contracts.contract_propagation import propagate_contract

                # Compute evolved contract: input contract + fields added by transform
                input_contract = token.row_data.contract
                evolved_contract = propagate_contract(
                    input_contract=input_contract,
                    output_row=result.row.to_dict(),
                    transform_adds_fields=True,
                )

                # Record to landscape for audit completeness
                self._recorder.update_node_output_contract(
                    run_id=ctx.run_id,
                    node_id=transform.node_id,
                    contract=evolved_contract,
                )

            # Update token with new PipelineRow, preserving all lineage metadata
            # For multi-row results, keep original row_data (engine will expand tokens later)
            if result.row is not None:
                # Single-row result: transforms return PipelineRow with correct contract
                slog.debug(
                    "pipeline_row_created",
                    token_id=token.token_id,
                    transform=transform.name,
                    contract_mode=result.row.contract.mode,
                )

                updated_token = token.with_updated_data(result.row)
            else:
                # Multi-row result: keep original row_data (engine will expand tokens later)
                updated_token = token.with_updated_data(token.row_data)
        else:
            # Transform returned error status (not exception)
            # This is a LEGITIMATE processing failure, not a bug
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=duration_ms,
                error=result.reason,
                context_after=result.context_after,
            )

            # Handle error routing - on_error is part of TransformProtocol
            on_error = transform.on_error
            # on_error is always set (required by TransformSettings) — Tier 1 invariant
            assert on_error is not None, (
                f"Transform '{transform.name}' has on_error=None — this should be impossible since TransformSettings requires on_error"
            )

            # Set error_sink so caller knows where the error was routed
            error_sink = on_error

            # Record error event (always, even for discard - audit completeness)
            # Use node_id (unique DAG identifier), not name (plugin type)
            # Bug fix: P2-2026-01-19-transform-errors-ambiguous-transform-id
            #
            # result.reason MUST be set for error results - TransformResult.error() requires it.
            # If None, that's a bug in the transform (constructed error result without reason).
            assert result.reason is not None, (
                f"Transform '{transform.name}' returned error but reason is None. "
                'Use TransformResult.error({{"reason": "...", ...}}) to create error results.'
            )
            ctx.record_transform_error(
                token_id=token.token_id,
                transform_id=transform.node_id,
                row=input_dict,  # Use extracted dict for Landscape recording
                error_details=result.reason,
                destination=on_error,
            )

            # Record DIVERT routing_event for audit trail (AUD-002).
            # This follows the same pattern as GateExecutor._record_routing():
            # the routing_event is recorded inside the executor where state_id
            # is in scope, co-located with the node_state lifecycle.
            if on_error != "discard":
                try:
                    error_edge_id = self._error_edge_ids[NodeID(transform.node_id)]
                except KeyError:
                    raise OrchestrationInvariantError(
                        f"Transform '{transform.node_id}' has on_error={on_error!r} but no "
                        f"DIVERT edge registered. DAG construction should have created an "
                        f"__error_{{name}}__ edge in from_plugin_instances()."
                    ) from None
                self._recorder.record_routing_event(
                    state_id=state.state_id,
                    edge_id=error_edge_id,
                    mode=RoutingMode.DIVERT,
                    reason=result.reason,
                )

            updated_token = token

        return result, updated_token, error_sink
