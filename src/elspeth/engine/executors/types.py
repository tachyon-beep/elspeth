# src/elspeth/engine/executors/types.py
"""Shared types for executor modules."""

from dataclasses import dataclass, field

from elspeth.contracts import TokenInfo
from elspeth.contracts.types import NodeID
from elspeth.plugins.results import GateResult


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


@dataclass
class GateOutcome:
    """Result of gate execution with routing information.

    Contains the gate result plus information about how the token
    should be routed and any child tokens created.
    """

    result: GateResult
    updated_token: TokenInfo
    child_tokens: list[TokenInfo] = field(default_factory=list)
    sink_name: str | None = None
    next_node_id: NodeID | None = None
