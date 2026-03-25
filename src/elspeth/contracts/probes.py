"""Collection readiness probes — protocols and result types.

Used by commencement gates (pre-flight checks) and retrieval provider
readiness contracts (transform pre-conditions).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CollectionReadinessResult:
    """Result of a collection readiness check.

    All fields are scalars — no __post_init__ freeze guard needed.
    """

    collection: str
    reachable: bool
    count: int
    message: str


@runtime_checkable
class CollectionProbe(Protocol):
    """Probes a vector store collection for readiness.

    Implementations live in L3 (plugins/infrastructure).
    The protocol is L0 so L2 (engine) can depend on it.
    """

    collection_name: str

    def probe(self) -> CollectionReadinessResult: ...
