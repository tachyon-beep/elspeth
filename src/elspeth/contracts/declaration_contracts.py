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

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, NotRequired, Protocol, Required, TypedDict, get_origin, get_type_hints, is_typeddict, runtime_checkable

from elspeth.contracts.audit_evidence import AuditEvidenceBase
from elspeth.contracts.freeze import deep_freeze, freeze_fields
from elspeth.contracts.secret_scrub import scrub_payload_for_audit
from elspeth.contracts.tier_registry import FrameworkBugError

# -----------------------------------------------------------------------------
# H5 Layer 1 — deny-by-default payload_schema (issue elspeth-3956044fb7)
# -----------------------------------------------------------------------------
#
# The ADR-010 §Decision 3 protocol already declares ``payload_schema`` on each
# contract. Layer 1 wires that schema onto the violation type so ``__init__``
# validates caller-supplied payload keys before the payload is deep-frozen.
# The base class inherits ``_EmptyPayload`` so the only legal base-class
# payload is ``{}`` — any concrete violation MUST subclass and override
# ``payload_schema`` with a purpose-built TypedDict.
#
# Why this matters: ``scrub_payload_for_audit`` is a closed-set defence
# (patterns + key names) and cannot cover every secret format that might
# appear in future contract payloads. The deny-by-default gate at
# construction flips the posture — a contract carrying an undeclared key
# cannot even be instantiated, so an unknown secret format cannot reach
# the Landscape audit record at all.


class _EmptyPayload(TypedDict):
    """Default ``DeclarationContractViolation.payload_schema``.

    Carries no keys. The only legal payload on the base class is ``{}``.
    Every concrete violation MUST subclass ``DeclarationContractViolation``
    and override ``payload_schema`` with a TypedDict that enumerates every
    key the violation's payload carries — this is the Layer 1 deny-by-default
    gate (issue elspeth-3956044fb7 / H5).
    """


def _resolve_typeddict_key_sets(schema: type) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(required, optional)`` frozensets for a TypedDict class.

    Implemented via ``typing.get_type_hints(schema, include_extras=True)``
    so ``NotRequired[...]`` / ``Required[...]`` wrappers survive even when
    the defining module uses ``from __future__ import annotations``. Under
    future annotations, TypedDict's own ``__required_keys__`` /
    ``__optional_keys__`` metaclass-populated attributes are unreliable
    because the class body's annotations are string literals the metaclass
    cannot parse at class-definition time — it defaults every key to the
    ``total`` flag's polarity and the Required/NotRequired wrappers are
    silently dropped. ``get_type_hints`` resolves the strings and
    ``typing.get_origin`` then yields the wrapper so author intent is
    preserved regardless of the caller's syntax.

    Each key is classified by:
      * If its origin is ``Required`` → required.
      * If its origin is ``NotRequired`` → optional.
      * Otherwise → follow the schema's class-level ``total`` flag
        (``total=True`` default → required; ``total=False`` → optional).

    Caller is responsible for confirming ``is_typeddict(schema)`` first;
    ``__total__`` access here would fail on non-TypedDict classes.
    """
    # ``is_typeddict(schema)`` was verified by the caller, so ``__total__``
    # exists. mypy does not narrow ``type`` through the typing discriminator,
    # so the runtime-verified access is suppressed at the call site below.
    total_required_default: bool = schema.__total__  # type: ignore[attr-defined]
    hints = get_type_hints(schema, include_extras=True)
    required: set[str] = set()
    optional: set[str] = set()
    for key, annotation in hints.items():
        origin = get_origin(annotation)
        if origin is Required:
            required.add(key)
        elif origin is NotRequired:
            optional.add(key)
        elif total_required_default:
            required.add(key)
        else:
            optional.add(key)
    return frozenset(required), frozenset(optional)


@dataclass(frozen=True, slots=True)
class RuntimeCheckInputs:
    """Bundle passed to ``DeclarationContract.runtime_check``.

    ``static_contract`` carries the DAG-validator-computed guarantee set for
    the current plugin's output (required by pass-through's verify_pass_through
    per pass_through.py:39). Contracts that do not need it can ignore it.

    ``override_input_fields`` lets the caller name the effective input-field
    set explicitly rather than have the contract derive it from
    ``input_row.contract.fields``. This exists because batch-flush
    TRANSFORM mode (``RowProcessor._cross_check_flush_output``) must check
    emitted rows against the *intersection* of every buffered token's
    contract (ADR-009 §Clause 2 batch-homogeneous semantics) — a shape the
    single ``input_row`` cannot express. Contracts that need the input
    fields MUST use ``override_input_fields`` when it is not ``None``;
    otherwise they fall back to ``input_row.contract.fields``. The
    single-token call site in ``TransformExecutor`` passes ``None``, so
    existing behaviour is unchanged there. ``frozenset`` is immutable so no
    freeze guard is required in ``__post_init__``.
    """

    plugin: Any
    node_id: str
    run_id: str
    row_id: str
    token_id: str
    input_row: Any
    static_contract: frozenset[str]
    override_input_fields: frozenset[str] | None = None


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

    **contract_name is dispatcher-attributed (issue elspeth-d74fe81529 / C4).**
    Contracts MUST NOT supply ``contract_name`` at construction; the
    declaration dispatcher (``run_runtime_checks``) catches the raised
    violation and attaches the authoritative name via
    ``_attach_contract_name`` before the exception propagates to the
    audit-recording boundary. This closes the contract-name spoofing vector
    where one contract's ``runtime_check`` could construct a violation
    labelled with another contract's name and corrupt the audit trail.

    ``contract_name`` is exposed as a read-only property; assigning to
    ``violation.contract_name`` after construction raises ``AttributeError``
    (the property has no setter). ``_attach_contract_name`` is one-shot —
    a second call raises ``RuntimeError``.

    ``__slots__`` names every identity field. ``BaseException`` unavoidably
    provides a ``__dict__`` so __slots__ is not a hard mutation guard for
    arbitrary attribute names; the property is. __slots__ is still declared
    for code-review discoverability and memory/speed on the named fields.
    """

    __slots__ = (
        "_contract_name",
        "node_id",
        "payload",
        "plugin",
        "row_id",
        "run_id",
        "token_id",
    )

    # H5 Layer 1 (issue elspeth-3956044fb7): deny-by-default payload schema.
    # Subclasses MUST override with a purpose-built TypedDict enumerating
    # every key the violation's ``payload`` can carry. The base class's
    # empty default accepts only ``payload={}``.
    payload_schema: ClassVar[type] = _EmptyPayload

    def __init__(
        self,
        *,
        plugin: str,
        node_id: str,
        run_id: str,
        row_id: str,
        token_id: str,
        payload: Mapping[str, Any],
        message: str,
    ) -> None:
        super().__init__(message)
        # H5 Layer 1: validate BEFORE deep-freeze. Deep-freeze is expensive
        # and pointless on a payload we're about to reject; raising first
        # also gives the caller a cleaner traceback pointing at the raw
        # dict they supplied rather than the frozen proxy.
        self._validate_payload_against_schema(payload)
        # Dispatcher attaches via _attach_contract_name before the violation
        # leaves run_runtime_checks. A None value here means the violation
        # was raised outside the dispatch path — the ``contract_name``
        # property will raise on read rather than silently serialize None.
        self._contract_name: str | None = None
        self.plugin = plugin
        self.node_id = node_id
        self.run_id = run_id
        self.row_id = row_id
        self.token_id = token_id
        # Deep-freeze so the attacker-under-debugger vector is closed (cannot
        # mutate between raise and record).
        self.payload: Mapping[str, Any] = deep_freeze(dict(payload))

    @classmethod
    def _validate_payload_against_schema(cls, payload: Mapping[str, Any]) -> None:
        """H5 Layer 1: enforce ``payload.keys() ⊆ allowed`` and
        ``required ⊆ payload.keys()`` against the class's ``payload_schema``.

        Key resolution uses ``typing.get_type_hints(..., include_extras=True)``
        rather than ``TypedDict.__required_keys__`` / ``__optional_keys__``.
        The metaclass-populated attributes are unreliable under
        ``from __future__ import annotations`` because ``NotRequired[...]``
        / ``Required[...]`` become string literals that the metaclass
        cannot parse at class-definition time. ``get_type_hints`` evaluates
        the strings at call time, after which ``get_origin(annotation)``
        correctly yields ``NotRequired`` / ``Required`` / ``None`` so the
        resolved required/optional sets match author intent regardless of
        whether the defining module uses future-annotation syntax.

        Raises:
            TypeError: ``payload_schema`` is not a TypedDict (canonical
                ``typing.is_typeddict`` check).
            ValueError: payload carries undeclared keys OR omits a required
                key. Messages include the schema name + the offending key
                set so the traceback identifies the culprit without a
                debugger round-trip.
        """
        schema = cls.payload_schema
        if not is_typeddict(schema):
            raise TypeError(
                f"{cls.__name__}.payload_schema must be a TypedDict "
                f"(got {schema!r}). Declare a purpose-built TypedDict "
                f"subclass for this violation's payload shape — this is "
                f"the H5 Layer 1 deny-by-default gate "
                f"(issue elspeth-3956044fb7)."
            )
        required_keys, optional_keys = _resolve_typeddict_key_sets(schema)
        allowed = required_keys | optional_keys
        payload_keys = frozenset(payload.keys())
        unknown = payload_keys - allowed
        if unknown:
            raise ValueError(
                f"{cls.__name__} payload contains undeclared keys "
                f"{sorted(unknown)!r}; schema {schema.__name__} allows "
                f"{sorted(allowed)!r}. Undeclared payload keys could "
                f"carry secret formats the scrubber does not yet "
                f"recognise — declare every key on the violation's "
                f"payload_schema TypedDict "
                f"(issue elspeth-3956044fb7 / H5 Layer 1)."
            )
        missing = required_keys - payload_keys
        if missing:
            raise ValueError(
                f"{cls.__name__} payload missing required keys "
                f"{sorted(missing)!r}; schema {schema.__name__} declares "
                f"{sorted(required_keys)!r} as required. Supply every "
                f"required key at construction time — the audit trail "
                f"needs all declared context for triage "
                f"(issue elspeth-3956044fb7 / H5 Layer 1)."
            )

    @property
    def contract_name(self) -> str:
        """Return the authoritative contract name attached by the dispatcher.

        Raises ``RuntimeError`` if the violation was raised outside the
        declaration-dispatch path — the audit trail requires an
        authoritative contract name and there is no safe fallback.
        """
        cn = self._contract_name
        if cn is None:
            raise RuntimeError(
                "DeclarationContractViolation.contract_name accessed before "
                "the dispatcher attached an authoritative name. This "
                "indicates the violation was raised outside "
                "run_runtime_checks (the declaration-dispatch boundary). "
                "All DeclarationContractViolation instances must propagate "
                "through the dispatcher so their contract_name can be "
                "derived from the firing contract's registry entry; "
                "caller-supplied names were removed to close the spoofing "
                "vector (issue elspeth-d74fe81529 / ADR-010 C4)."
            )
        return cn

    def _attach_contract_name(self, name: str) -> None:
        """One-shot setter for the authoritative contract name.

        Called by the declaration dispatcher (``run_runtime_checks``) after a
        violation is raised and before it propagates to the audit-recording
        boundary. A second call raises ``RuntimeError`` to catch double-
        attachment bugs in the dispatcher or any other code path that
        shouldn't be writing this field.

        The underscore prefix signals private API; ``contract_name`` is the
        public read-only surface.
        """
        if self._contract_name is not None:
            raise RuntimeError(
                f"DeclarationContractViolation._attach_contract_name called "
                f"twice: already set to {self._contract_name!r}, refused "
                f"overwrite with {name!r}. This indicates a dispatcher or "
                f"exception-handling bug — the authoritative name is set "
                f"exactly once per violation lifecycle."
            )
        self._contract_name = name

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


# -----------------------------------------------------------------------------
# EXPECTED_CONTRACTS manifest (ADR-010 §Decision 3, issue elspeth-b03c6112c0 / C2)
# -----------------------------------------------------------------------------
#
# Every declaration contract registered at orchestrator bootstrap MUST be
# listed here. The bootstrap check (``prepare_for_run()``) asserts set
# *equality* between the registered names and this manifest — not merely
# non-empty — so that a conditional/forgotten module import that silently
# skips a contract registration fails loudly instead of being recorded as
# "compliant" in the audit trail.
#
# Adding or removing a contract requires updating this manifest in the SAME
# commit that adds/removes the registration call site. ``scripts/cicd/
# enforce_contract_manifest.py`` scans the source tree and fails CI if the
# manifest drifts from the registration call sites.
#
# CLOSED SET — do not extend without adding the matching
# ``register_declaration_contract(...)`` call site in the same commit.
EXPECTED_CONTRACTS: frozenset[str] = frozenset(
    {
        # PassThroughDeclarationContract
        #   Defined:     src/elspeth/engine/executors/pass_through.py
        #   Registered:  src/elspeth/engine/executors/pass_through.py (module-import side-effect)
        #   ADR:         ADR-007 / ADR-008 / ADR-010
        "passes_through_input",
    }
)


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


def _require_pytest_process(helper_name: str) -> None:
    """Single pytest-process gate for every test-only registry helper.

    Enforces the ADR-010 §Decision 3 invariant that test-only mutation
    helpers must never execute outside a pytest worker. The gate is
    ``"pytest" in sys.modules`` — this is true under both the main pytest
    runner and xdist subprocesses (which import pytest by design), and
    false under any production interpreter. **It is the ONLY unlock
    path.** An ``ELSPETH_TESTING=1`` env-var arm previously also
    unlocked these helpers; issue elspeth-cc511e7234 (C3) removed it
    because any process capable of setting an environment variable
    (CI misconfiguration, parent-process env leakage, operator error,
    attacker with env-write capability) could silently clear all
    runtime VAL contracts in production. Declarative invariants that
    can be disabled by an environment variable are not invariants.
    """
    if "pytest" not in sys.modules:
        raise RuntimeError(
            f"{helper_name} called outside a pytest process. This helper "
            "must never run in production — doing so silently disables all "
            "runtime VAL checks. No environment variable or other side-channel "
            "unlock exists: the helper is pytest-gated by design."
        )


def _clear_registry_for_tests() -> None:
    """Test-only: wipe the registry AND reset the freeze flag.

    Gated on ``pytest`` being imported. A production caller raises
    ``RuntimeError`` — this helper must never run in a live orchestrator
    process (reviewer B5/B9, issue elspeth-cc511e7234)."""
    global _FROZEN
    _require_pytest_process("_clear_registry_for_tests")
    _REGISTRY.clear()
    _FROZEN = False


def _snapshot_registry_for_tests() -> tuple[list[DeclarationContract], bool]:
    """Test-only: return a snapshot of (registry_copy, frozen_flag).

    Pair with ``_restore_registry_snapshot_for_tests`` to save/restore across
    test boundaries. Gated on ``pytest`` being imported. Production callers
    raise (issue elspeth-cc511e7234)."""
    _require_pytest_process("_snapshot_registry_for_tests")
    return list(_REGISTRY), _FROZEN


def _restore_registry_snapshot_for_tests(
    snapshot: tuple[list[DeclarationContract], bool],
) -> None:
    """Test-only: restore the registry and freeze flag from a snapshot.

    Gated on ``pytest`` being imported. Production callers raise (issue
    elspeth-cc511e7234)."""
    global _FROZEN
    _require_pytest_process("_restore_registry_snapshot_for_tests")
    registry_copy, frozen_flag = snapshot
    _REGISTRY.clear()
    _REGISTRY.extend(registry_copy)
    _FROZEN = frozen_flag
