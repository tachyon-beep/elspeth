"""Secret resolution contracts — shared across CLI and web.

Layer: L0 (contracts). No upward imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ResolvedSecret:
    """A resolved secret value with provenance metadata.

    The value field carries plaintext for in-process runtime use ONLY.
    It must NEVER be persisted, logged, or returned in any API response.
    """

    name: str
    value: str
    scope: Literal["user", "server", "org"]
    fingerprint: str

    def __repr__(self) -> str:
        return f"ResolvedSecret(name={self.name!r}, scope={self.scope!r}, fingerprint={self.fingerprint!r})"

    def __str__(self) -> str:
        return f"ResolvedSecret({self.name}, scope={self.scope})"


@dataclass(frozen=True, slots=True)
class SecretInventoryItem:
    """Browser-safe secret metadata — no value, no masked derivative."""

    name: str
    scope: str
    available: bool
    source_kind: str = ""


@runtime_checkable
class WebSecretResolver(Protocol):
    """Protocol for web-facing secret resolution and inventory."""

    def list_refs(self, user_id: str) -> list[SecretInventoryItem]: ...

    def has_ref(self, user_id: str, name: str) -> bool: ...

    def resolve(self, user_id: str, name: str) -> ResolvedSecret | None: ...
