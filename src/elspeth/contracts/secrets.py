"""Secret resolution contracts — shared across CLI and web.

Layer: L0 (contracts). No upward imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

SecretScope = Literal["user", "server", "org"]
_ALLOWED_SECRET_SCOPES = frozenset({"user", "server", "org"})
_LOWERCASE_HEX = frozenset("0123456789abcdef")


def _validate_secret_scope(owner: str, scope: SecretScope) -> None:
    if scope not in _ALLOWED_SECRET_SCOPES:
        raise ValueError(f"{owner}: scope must be one of {sorted(_ALLOWED_SECRET_SCOPES)}, got {scope!r}")


def _validate_secret_fingerprint(owner: str, fingerprint: str) -> None:
    if len(fingerprint) != 64 or any(ch not in _LOWERCASE_HEX for ch in fingerprint):
        raise ValueError(f"{owner}: fingerprint must be 64-char lowercase hex, got {fingerprint!r}")


class SecretsError(Exception):
    """Base for all secrets-subsystem errors.

    Raised by stores/services and caught by the HTTP application layer
    (web/app.py exception handlers) or the pipeline resolution path
    (core/secrets.resolve_secret_refs).  Callers that want a generic
    "something about secrets went wrong" catch should target this base
    class; tests that need to discriminate failure modes should target
    the specific subclasses below.
    """


class SecretsConfigurationError(SecretsError):
    """Deployment-level misconfiguration preventing a secret operation.

    Semantically distinct from user-input errors: the operator must fix
    server configuration, not the API consumer.  HTTP handlers map this
    family to 503 Service Unavailable so clients know the request was
    well-formed and retrying won't help until configuration changes.
    """


class FingerprintKeyMissingError(SecretsConfigurationError):
    """``ELSPETH_FINGERPRINT_KEY`` is not set.

    Without the fingerprint key, audit fingerprints cannot be computed.
    CLAUDE.md's audit-primacy rule requires the audit record to precede
    any persistent write, so a secret write that cannot be fingerprinted
    must fail atomically rather than store an unfingerprinted row.
    """


class SecretDecryptionError(SecretsError):
    """Stored ciphertext cannot be decrypted with the current master key.

    Typical causes: master-key rotation, row corruption, or tampering.
    HTTP handlers map this to 409 Conflict — the request was well-formed
    but the stored state conflicts with current server configuration;
    the caller recovers by re-saving the secret.

    The pipeline resolution path (WebSecretService.resolve) continues to
    translate this into ``None`` so batched secret resolution treats the
    row as missing rather than propagating a 500 through run startup;
    HTTP callers see the explicit error only on direct validate/create
    endpoints where the explicit failure is actionable.
    """


@dataclass(frozen=True, slots=True)
class CreateSecretResult:
    """Outcome of a successful ``WebSecretService.set_user_secret`` call.

    Eager-fingerprint design guarantees that if this value is returned
    (rather than an exception being raised), the secret is both persisted
    AND immediately resolvable — closing the TOCTOU window that the
    prior two-step ``set_secret`` + ``has_ref`` check suffered.

    ``fingerprint`` is safe to surface — it is an HMAC digest, not the
    secret value, and is already recorded in the Landscape audit trail
    for correlation.
    """

    name: str
    scope: SecretScope
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_secret_scope(type(self).__name__, self.scope)
        _validate_secret_fingerprint(type(self).__name__, self.fingerprint)


@dataclass(frozen=True, slots=True)
class ResolvedSecret:
    """A resolved secret value with provenance metadata.

    The value field carries plaintext for in-process runtime use ONLY.
    It must NEVER be persisted, logged, or returned in any API response.
    """

    name: str
    value: str
    scope: SecretScope
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_secret_scope(type(self).__name__, self.scope)
        _validate_secret_fingerprint(type(self).__name__, self.fingerprint)

    def __repr__(self) -> str:
        return f"ResolvedSecret(name={self.name!r}, scope={self.scope!r}, fingerprint={self.fingerprint!r})"

    def __str__(self) -> str:
        return f"ResolvedSecret({self.name}, scope={self.scope})"


@dataclass(frozen=True, slots=True)
class SecretInventoryItem:
    """Browser-safe secret metadata — no value, no masked derivative.

    ``scope`` is narrowed to the production domain so it matches
    ``CreateSecretResult.scope`` and ``ResolvedSecret.scope``: type-checked
    callers cannot pass an invented scope value through the inventory
    without first widening this Literal and every sibling schema.
    """

    name: str
    scope: SecretScope
    available: bool
    source_kind: str = ""

    def __post_init__(self) -> None:
        _validate_secret_scope(type(self).__name__, self.scope)


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
