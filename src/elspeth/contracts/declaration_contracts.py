"""DeclarationContract protocol + registry + violation base (ADR-010 §Decision 3).

Protocol shape in 2A:

- ``name: str`` — unique identifier.
- ``applies_to(plugin) -> bool`` — gate for the dispatcher.
- ``runtime_check(inputs, outputs) -> None`` — per-row verification.
- ``payload_schema: type[TypedDict]`` — schema for the violation payload.
- ``negative_example() -> tuple[RuntimeCheckInputs, RuntimeCheckOutputs]`` —
  classmethod returning a scenario that MUST trigger runtime_check to raise
  the contract's violation.

``static_check`` is intentionally absent in 2A (see plan Revision History —
Review v1 B1/B11). The walker refactor stays in Phase 2B.

``DeclarationContractViolation`` inherits AuditEvidenceBase (nominal), carries
a deep-frozen payload that is scrubbed for secrets before serialization.

Registry freezes at end of orchestrator bootstrap (see Task 5b).
``_clear_registry_for_tests`` is pytest-gated; production callers raise.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from elspeth.contracts.audit_evidence import AuditEvidenceBase
from elspeth.contracts.freeze import deep_freeze, freeze_fields
from elspeth.contracts.secret_scrub import scrub_payload_for_audit
from elspeth.contracts.tier_registry import FrameworkBugError


@dataclass(frozen=True, slots=True)
class RuntimeCheckInputs:
    """Bundle passed to ``DeclarationContract.runtime_check``.

    ``static_contract`` carries the DAG-validator-computed guarantee set for
    the current plugin's output (required by pass-through's verify_pass_through
    per pass_through.py:39). Contracts that do not need it can ignore it.
    """

    plugin: Any
    node_id: str
    run_id: str
    row_id: str
    token_id: str
    input_row: Any
    static_contract: frozenset[str]


@dataclass(frozen=True, slots=True)
class RuntimeCheckOutputs:
    """Emitted-rows bundle. ``emitted_rows`` is normalized to a deep-frozen
    ``tuple`` in ``__post_init__``. Inputs must be ``list`` or ``tuple`` —
    arbitrary ``Sequence`` subtypes (including lazy wrappers) crash loudly
    rather than silently bypass the freeze guard. See CLAUDE.md §Frozen
    Dataclass Immutability + §Offensive Programming.
    """

    emitted_rows: tuple[Any, ...]

    def __post_init__(self) -> None:
        # Cast to ``object`` so mypy does not pre-narrow via the declared field
        # type (tuple[Any, ...]) and flag the ``isinstance(value, list)`` branch
        # as unreachable. At runtime callers may pass any sequence subtype; the
        # guard catches and rejects non-list/non-tuple inputs offensively.
        value: object = self.emitted_rows
        if isinstance(value, list):
            object.__setattr__(
                self,
                "emitted_rows",
                tuple(deep_freeze(item) for item in value),
            )
        elif isinstance(value, tuple):
            freeze_fields(self, "emitted_rows")
        else:
            raise TypeError(f"RuntimeCheckOutputs.emitted_rows must be list or tuple, got {type(value).__name__!r}")


class DeclarationContractViolation(AuditEvidenceBase, RuntimeError):
    """Generic audit-evidence-bearing violation for declaration contracts.

    Individual contracts may subclass this to add stronger typing; the base
    form is sufficient for contracts whose payload is a simple mapping.

    The ``payload`` is deep-frozen in ``__init__`` (reviewer B12) and scrubbed
    for secrets via ``scrub_payload_for_audit`` before ``to_audit_dict``
    returns it (reviewer B7/F-4). The scrub is applied at serialization time
    so the stored payload keeps full information for in-process diagnostics
    while the Landscape record gets the redacted form.
    """

    def __init__(
        self,
        *,
        contract_name: str,
        plugin: str,
        node_id: str,
        run_id: str,
        row_id: str,
        token_id: str,
        payload: Mapping[str, Any],
        message: str,
    ) -> None:
        super().__init__(message)
        self.contract_name = contract_name
        self.plugin = plugin
        self.node_id = node_id
        self.run_id = run_id
        self.row_id = row_id
        self.token_id = token_id
        # Deep-freeze so the attacker-under-debugger vector is closed (cannot
        # mutate between raise and record).
        self.payload: Mapping[str, Any] = deep_freeze(dict(payload))

    def to_audit_dict(self) -> Mapping[str, Any]:
        return {
            "exception_type": type(self).__name__,
            "contract_name": self.contract_name,
            "plugin": self.plugin,
            "node_id": self.node_id,
            "run_id": self.run_id,
            "row_id": self.row_id,
            "token_id": self.token_id,
            "payload": scrub_payload_for_audit(self.payload),
            "message": str(self),
        }


@runtime_checkable
class DeclarationContract(Protocol):
    """Protocol every declaration-trust contract satisfies.

    Used for static type-checking and test diagnostics. The dispatcher does
    NOT rely on ``isinstance(contract, DeclarationContract)`` at the call
    site — it iterates ``registered_declaration_contracts()`` which returns
    concrete instances already proven to satisfy the protocol at registration
    time.
    """

    name: str
    payload_schema: type  # must be a TypedDict class

    def applies_to(self, plugin: Any) -> bool: ...
    def runtime_check(self, inputs: RuntimeCheckInputs, outputs: RuntimeCheckOutputs) -> None: ...

    @classmethod
    def negative_example(cls) -> tuple[RuntimeCheckInputs, RuntimeCheckOutputs]: ...


_REGISTRY: list[DeclarationContract] = []
_FROZEN: bool = False


def register_declaration_contract(contract: DeclarationContract) -> None:
    """Register a contract. Validates protocol shape and uniqueness.

    Raises:
        FrameworkBugError: registry is frozen (post-bootstrap).
        ValueError: duplicate ``name``.
        TypeError: ``payload_schema`` missing, not a type, or ``negative_example``
            not callable.
    """
    if _FROZEN:
        raise FrameworkBugError(f"Cannot register {contract.name!r}: declaration-contract registry is frozen.")

    # Validate payload_schema presence and type.
    # We use try/except AttributeError (not hasattr — banned by CLAUDE.md) to
    # detect a missing attribute at this registration trust boundary.
    try:
        payload_schema = contract.payload_schema
    except AttributeError:
        raise TypeError(f"Contract {contract.name!r} missing required payload_schema attribute") from None
    if not isinstance(payload_schema, type):
        raise TypeError(f"Contract {contract.name!r} payload_schema must be a type (TypedDict subclass)")

    # Validate negative_example presence and callability.
    # Access via type(contract) to detect the classmethod on the class, not an
    # instance attribute. Try/except AttributeError instead of hasattr (banned).
    try:
        neg_example = type(contract).negative_example
    except AttributeError:
        raise TypeError(f"Contract {contract.name!r} missing required negative_example classmethod") from None
    if not callable(neg_example):
        raise TypeError(f"Contract {contract.name!r} negative_example must be callable")

    for existing in _REGISTRY:
        if existing.name == contract.name:
            raise ValueError(f"duplicate contract name {contract.name!r}: already registered")
    _REGISTRY.append(contract)


def registered_declaration_contracts() -> Sequence[DeclarationContract]:
    return tuple(_REGISTRY)


def freeze_declaration_registry() -> None:
    """Seal the registry. Subsequent ``register_declaration_contract`` calls
    raise ``FrameworkBugError``. Called at end of orchestrator bootstrap."""
    global _FROZEN
    _FROZEN = True


def declaration_registry_is_frozen() -> bool:
    """Return whether the registry has been sealed by bootstrap.

    Used by ``prepare_for_run()`` to skip the non-empty assertion and
    re-freeze on subsequent calls when the registry is already sealed (e.g.
    when ``Orchestrator.run()`` is invoked more than once in a single
    process with the same registry state).
    """
    return _FROZEN


def _clear_registry_for_tests() -> None:
    """Test-only: wipe the registry AND reset the freeze flag.

    Gated on ``pytest`` being imported OR ``ELSPETH_TESTING=1`` env var. A
    production caller will raise ``RuntimeError`` — this helper must never
    run in a live orchestrator process (reviewer B5/B9)."""
    global _FROZEN
    if "pytest" not in sys.modules and os.environ.get("ELSPETH_TESTING") != "1":
        raise RuntimeError(
            "_clear_registry_for_tests called outside a pytest process and "
            "without ELSPETH_TESTING=1. Production code MUST NOT clear the "
            "declaration-contract registry — doing so silently disables all "
            "runtime VAL checks."
        )
    _REGISTRY.clear()
    _FROZEN = False
