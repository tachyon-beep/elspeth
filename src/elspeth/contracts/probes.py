"""Collection readiness probes — protocols and result types.

Used by commencement gates (pre-flight checks) and retrieval provider
readiness contracts (transform pre-conditions).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from elspeth.contracts.freeze import require_int


@dataclass(frozen=True, slots=True)
class CollectionReadinessResult:
    """Result of a collection readiness check.

    All fields are scalars — no freeze guard needed. Validates non-empty collection
    and non-negative count.
    """

    collection: str
    reachable: bool
    count: int
    message: str

    def __post_init__(self) -> None:
        if not self.collection:
            raise ValueError("collection must not be empty")
        require_int(self.count, "count", min_value=0)
        if not self.reachable and self.count != 0:
            raise ValueError(f"Contradictory state: reachable=False but count={self.count}. Unreachable collections must report count=0.")


@runtime_checkable
class CollectionProbe(Protocol):
    """Probes a vector store collection for readiness.

    Implementations live in L3 (plugins/infrastructure).
    The protocol is L0 so L2 (engine) can depend on it.
    """

    collection_name: str

    def probe(self) -> CollectionReadinessResult: ...
