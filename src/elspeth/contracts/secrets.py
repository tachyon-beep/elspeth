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

    def has_ref(self, user_id: str, name: str) -> bool:
        """Check whether *name* is resolvable — not merely whether it exists.

        Implementations MUST return True only when all prerequisites for
        ``resolve()`` are met: the secret exists, any required encryption
        keys are available, and any deployment-level configuration (e.g.
        ELSPETH_FINGERPRINT_KEY for audit fingerprints) is present.

        Callers (pipeline validation, composer tools) treat ``has_ref()``
        as a preflight guarantee that ``resolve()`` will succeed.  If
        ``has_ref()`` returns True but ``resolve()`` later fails, the
        pipeline passes validation and fails at execution — a contract
        violation.
        """
        ...

    def resolve(self, user_id: str, name: str) -> ResolvedSecret | None: ...
