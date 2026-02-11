# src/elspeth/engine/executors/gate.py
"""GateExecutor - wraps config-driven gates with audit recording and routing."""

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from elspeth.contracts import (
    ConfigGateReason,
    ExecutionError,
    RouteDestination,
    RouteDestinationKind,
    RoutingAction,
    RoutingReason,
    RoutingSpec,
    TokenInfo,
)
from elspeth.contracts.enums import (
    NodeStateStatus,
    RoutingMode,
)
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.types import NodeID, StepResolver
from elspeth.core.canonical import stable_hash
from elspeth.core.config import GateSettings
from elspeth.core.landscape import LandscapeRecorder
from elspeth.engine.executors.types import GateOutcome, MissingEdgeError
from elspeth.engine.expression_parser import ExpressionParser
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.results import GateResult

if TYPE_CHECKING:
    from elspeth.engine.tokens import TokenManager

logger = logging.getLogger(__name__)
slog = structlog.get_logger(__name__)


@dataclass
class _RouteDispatchOutcome:
    """Internal routing dispatch result used by gate executors."""

    action: RoutingAction
    child_tokens: list[TokenInfo] = field(default_factory=list)
    sink_name: str | None = None
    next_node_id: NodeID | None = None


class GateExecutor:
    """Executes gates with audit recording and routing.

    Wraps gate.evaluate() to:
    1. Record node state start
    2. Time the operation
    3. Populate audit fields in result
    4. Record routing events
    5. Create child tokens for fork operations
    6. Record node state completion
    7. Emit OpenTelemetry span

    CRITICAL: Status is always "completed" for successful gate execution.
    Terminal state (ROUTED, FORKED) is DERIVED from routing_events/token_parents,
    NOT stored in node_states.status.

    Example:
        executor = GateExecutor(recorder, span_factory, step_resolver, edge_map)
        outcome = executor.execute_config_gate(
            gate_config=gate_settings,
            node_id=node_id,
            token=token,
            ctx=ctx,
            token_manager=manager,  # Required for fork destinations
        )
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        span_factory: SpanFactory,
        step_resolver: StepResolver,
        edge_map: dict[tuple[NodeID, str], str] | None = None,
        route_resolution_map: dict[tuple[NodeID, str], RouteDestination] | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            recorder: Landscape recorder for audit trail
            span_factory: Span factory for tracing
            step_resolver: Resolves NodeID to 1-indexed audit step position
            edge_map: Maps (node_id, label) -> edge_id for routing
            route_resolution_map: Maps (node_id, label) -> resolved route destination
        """
        self._recorder = recorder
        self._spans = span_factory
        self._step_resolver = step_resolver
        self._edge_map = edge_map or {}
        self._route_resolution_map = route_resolution_map or {}

    def _resolve_route_destination(self, *, node_id: str, route_label: str) -> RouteDestination:
        """Resolve route label to concrete destination or fail closed."""
        try:
            return self._route_resolution_map[(NodeID(node_id), route_label)]
        except KeyError:
            raise MissingEdgeError(node_id=NodeID(node_id), label=route_label) from None

    def _dispatch_resolved_destination(
        self,
        *,
        state_id: str,
        node_id: str,
        route_label: str,
        destination: RouteDestination,
        token: TokenInfo,
        ctx: PluginContext,
        token_manager: "TokenManager | None",
        reason: RoutingReason | None,
        mode: RoutingMode,
        fork_branches: list[str] | None,
        continue_as_route: bool,
    ) -> _RouteDispatchOutcome:
        """Dispatch CONTINUE/FORK/SINK/PROCESSING_NODE destinations."""
        if destination.kind == RouteDestinationKind.CONTINUE:
            if continue_as_route:
                action = RoutingAction.route("continue", mode=mode, reason=reason)
            else:
                action = RoutingAction.continue_(reason=reason)
            self._record_routing(
                state_id=state_id,
                node_id=node_id,
                action=action,
            )
            return _RouteDispatchOutcome(action=action)

        if destination.kind == RouteDestinationKind.FORK:
            if fork_branches is None:
                raise OrchestrationInvariantError(
                    f"Gate {node_id} route '{route_label}' resolved to fork but no fork branches are configured"
                )
            if token_manager is None:
                raise OrchestrationInvariantError(
                    f"Gate {node_id} routes to fork but no TokenManager provided. "
                    "Cannot create child tokens - audit integrity would be compromised."
                )

            action = RoutingAction.fork_to_paths(fork_branches, reason=reason)
            self._record_routing(
                state_id=state_id,
                node_id=node_id,
                action=action,
            )
            child_tokens, _fork_group_id = token_manager.fork_token(
                parent_token=token,
                branches=fork_branches,
                node_id=NodeID(node_id),
                run_id=ctx.run_id,
                row_data=token.row_data,
            )
            return _RouteDispatchOutcome(action=action, child_tokens=child_tokens)

        route_action = RoutingAction.route(route_label, mode=mode, reason=reason)
        self._record_routing(
            state_id=state_id,
            node_id=node_id,
            action=route_action,
        )
        if destination.kind == RouteDestinationKind.SINK:
            return _RouteDispatchOutcome(action=route_action, sink_name=destination.sink_name)
        if destination.kind == RouteDestinationKind.PROCESSING_NODE:
            return _RouteDispatchOutcome(action=route_action, next_node_id=destination.next_node_id)

        raise OrchestrationInvariantError(f"Unsupported route destination kind '{destination.kind}' for gate {node_id}")

    def execute_config_gate(
        self,
        gate_config: GateSettings,
        node_id: str,
        token: TokenInfo,
        ctx: PluginContext,
        token_manager: "TokenManager | None" = None,
    ) -> GateOutcome:
        """Execute a config-driven gate using ExpressionParser.

        Evaluates the gate condition directly using the expression parser.
        The condition expression is evaluated against the token's row_data.

        Route Resolution:
        - If condition returns a string, it's used as the route label directly
        - If condition returns a boolean, it's converted to "true"/"false" label
        - The label is then looked up in gate_config.routes to get the destination

        The step position in the DAG is resolved internally via StepResolver
        using node_id, rather than being passed as a parameter.

        Args:
            gate_config: Gate configuration with condition and routes
            node_id: Node ID assigned by orchestrator
            token: Current token with row data
            ctx: Plugin context
            token_manager: TokenManager for fork operations (required for fork destinations)

        Returns:
            GateOutcome with result, updated token, and routing info

        Raises:
            MissingEdgeError: If routing refers to an unregistered edge
            ValueError: If condition result doesn't match any route label
            RuntimeError: If fork destination without token_manager
        """
        # Resolve step position from node_id (injected StepResolver)
        step = self._step_resolver(NodeID(node_id))

        # Extract dict from PipelineRow for hashing and Landscape recording
        # Landscape stores raw dicts, not PipelineRow objects
        input_dict = token.row_data.to_dict()
        input_hash = stable_hash(input_dict)

        # Begin node state with dict (for Landscape recording)
        state = self._recorder.begin_node_state(
            token_id=token.token_id,
            node_id=node_id,
            run_id=ctx.run_id,
            step_index=step,
            input_data=input_dict,
        )

        # Set ctx.contract for plugins that use fallback access (dual-name resolution)
        ctx.contract = token.row_data.contract

        # Create parser and evaluate condition
        # P2-2026-01-21: Pass token_id for accurate child token attribution in traces
        # P2-2026-01-21: Pass node_id for disambiguation when multiple config gates exist
        with self._spans.gate_span(
            gate_config.name,
            node_id=node_id,
            input_hash=input_hash,
            token_id=token.token_id,
        ):
            start = time.perf_counter()
            try:
                parser = ExpressionParser(gate_config.condition)
                # Pass PipelineRow directly - it implements __getitem__ and .get()
                # This preserves dual-name access (normalized and original field names)
                eval_result = parser.evaluate(token.row_data)
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
                raise

        # Convert evaluation result to route label
        if isinstance(eval_result, bool):
            route_label = "true" if eval_result else "false"
        elif isinstance(eval_result, str):
            route_label = eval_result
        else:
            # Unexpected result type - convert to string
            route_label = str(eval_result)

        # Look up destination in routes config
        if route_label not in gate_config.routes:
            # Record failure before raising
            error = {
                "exception": f"Route label '{route_label}' not found in routes config",
                "type": "ValueError",
            }
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=duration_ms,
                error=error,
            )
            raise ValueError(
                f"Gate '{gate_config.name}' condition returned '{route_label}' which is not in routes: {list(gate_config.routes.keys())}"
            )

        # Build routing action and process based on destination
        action = RoutingAction.continue_(reason={"condition": gate_config.condition, "result": route_label})
        child_tokens: list[TokenInfo] = []
        sink_name: str | None = None
        next_node_id: NodeID | None = None
        reason: ConfigGateReason = {"condition": gate_config.condition, "result": route_label}

        try:
            destination = self._resolve_route_destination(node_id=node_id, route_label=route_label)
            dispatch = self._dispatch_resolved_destination(
                state_id=state.state_id,
                node_id=node_id,
                route_label=route_label,
                destination=destination,
                token=token,
                ctx=ctx,
                token_manager=token_manager,
                reason=reason,
                mode=RoutingMode.MOVE,
                fork_branches=gate_config.fork_to,
                continue_as_route=False,
            )
            action = dispatch.action
            child_tokens = dispatch.child_tokens
            sink_name = dispatch.sink_name
            next_node_id = dispatch.next_node_id

        except MissingEdgeError as e:
            # Record failure before re-raising - ensures node_state is never left OPEN
            routing_error: ExecutionError = {
                "exception": str(e),
                "type": type(e).__name__,
            }
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=duration_ms,
                error=routing_error,
            )
            raise

        # Create GateResult for audit fields
        # Config gates don't modify data, so use input dict as output
        result = GateResult(
            row=input_dict,
            action=action,
            contract=token.row_data.contract,  # Preserve contract reference
        )
        result.input_hash = input_hash
        result.output_hash = stable_hash(input_dict)  # Same as input (no modification)
        result.duration_ms = duration_ms

        # Complete node state - always "completed" for successful execution
        # Terminal state is DERIVED from routing_events, not stored here
        self._recorder.complete_node_state(
            state_id=state.state_id,
            status=NodeStateStatus.COMPLETED,
            output_data=input_dict,  # Landscape stores dict, not PipelineRow
            duration_ms=duration_ms,
        )

        # Token row_data is unchanged (config gates don't modify data)
        # PipelineRow is already set on token, so just preserve it
        updated_token = token.with_updated_data(token.row_data)

        return GateOutcome(
            result=result,
            updated_token=updated_token,
            child_tokens=child_tokens,
            sink_name=sink_name,
            next_node_id=next_node_id,
        )

    def _record_routing(
        self,
        state_id: str,
        node_id: str,
        action: "RoutingAction",
    ) -> None:
        """Record routing events for a routing action.

        Raises:
            MissingEdgeError: If any destination has no registered edge.
        """
        typed_node_id = NodeID(node_id)
        if len(action.destinations) == 1:
            dest = action.destinations[0]
            edge_id = self._edge_map.get((typed_node_id, dest))
            if edge_id is None:
                raise MissingEdgeError(node_id=typed_node_id, label=dest)

            self._recorder.record_routing_event(
                state_id=state_id,
                edge_id=edge_id,
                mode=action.mode,
                reason=action.reason,
            )
        else:
            # Multiple destinations (fork)
            routes = []
            for dest in action.destinations:
                edge_id = self._edge_map.get((typed_node_id, dest))
                if edge_id is None:
                    raise MissingEdgeError(node_id=typed_node_id, label=dest)
                routes.append(RoutingSpec(edge_id=edge_id, mode=action.mode))

            self._recorder.record_routing_events(
                state_id=state_id,
                routes=routes,
                reason=action.reason,
            )
