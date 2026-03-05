"""Shared types for executor modules."""

from dataclasses import dataclass

from elspeth.contracts import GateResult, TokenInfo
from elspeth.contracts.types import NodeID


class MissingEdgeError(Exception):
    """Raised when routing refers to an unregistered edge.

    This is an audit integrity error - every routing decision must be
    traceable to a registered edge. Silent edge loss is unacceptable.
    """

    def __init__(self, node_id: NodeID, label: str) -> None:
        """Initialize with routing details.

        Args:
            node_id: Node that attempted routing
            label: Edge label that was not found
        """
        self.node_id = node_id
        self.label = label
        super().__init__(
            f"No edge registered from node {node_id} with label '{label}'. Audit trail would be incomplete - refusing to proceed."
        )


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """Result of gate execution with routing information.

    Contains the gate result plus information about how the token
    should be routed and any child tokens created.

    Invariant: sink_name and next_node_id are mutually exclusive.
    A gate routes to a sink OR jumps to a node, never both.
    """

    result: GateResult
    updated_token: TokenInfo
    child_tokens: tuple[TokenInfo, ...] = ()
    sink_name: str | None = None
    next_node_id: NodeID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_tokens", tuple(self.child_tokens))
        if self.sink_name is not None and self.next_node_id is not None:
            raise ValueError(
                f"GateOutcome invariant violation: sink_name={self.sink_name!r} and "
                f"next_node_id={self.next_node_id!r} are mutually exclusive. "
                f"A gate routes to a sink OR jumps to a node, not both."
            )
