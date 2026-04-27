"""Structured execution-layer exceptions.

SemanticContractViolationError carries the same structured records as
the /validate endpoint surfaces, so callers of /execute that need to
render structured errors (frontend banner, MCP error payload) can do
so instead of falling back to string parsing.

Subclassing ValueError preserves backward compatibility for any caller
catching ValueError today; new callers should catch the specific type
to access entries and contracts.
"""

from __future__ import annotations

from elspeth.contracts.plugin_semantics import SemanticEdgeContract
from elspeth.web.composer.state import ValidationEntry


class SemanticContractViolationError(ValueError):
    """Raised when /execute pre-run semantic validation rejects the pipeline.

    Subclasses ValueError so existing ``except ValueError`` paths still
    catch it; new code should catch ``SemanticContractViolationError``
    directly to access the structured payload.
    """

    def __init__(
        self,
        *,
        entries: tuple[ValidationEntry, ...],
        contracts: tuple[SemanticEdgeContract, ...],
    ) -> None:
        self.entries = entries
        self.contracts = contracts
        message = "; ".join(entry.message for entry in entries)
        super().__init__(message)
