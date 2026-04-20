"""DeclarationContract framework (ADR-010 §Decision 3, amended 2026-04-20).

H2 landing (issue elspeth-425047a599): the 2A single-site protocol is extended
to a 4-site nominal-ABC framework with collect-then-raise audit-complete
dispatch (ADR-010 §Semantics, anchored at comment #417 on H2).

## Public surface

- ``DispatchSite`` — StrEnum naming the four dispatch sites.
- ``@implements_dispatch_site("site_name")`` — method decorator claiming a
  dispatch site. The authoritative signal under multi-level inheritance
  (AST scanner cannot reliably see mixin-inherited overrides). **Layer L0**
  placement is mandatory per plan-review W4 — the CI scanner at L3 imports
  it, and concrete contracts at L2/L3 apply it.
- ``DeclarationContract`` — nominal ABC every contract inherits. Declares
  four dispatch methods with default no-op bodies (decorate to claim).
  Rejected Protocol alternative per ADR-010 §Alternative 3 (nominal closes
  the spoofing vector).
- Bundle types — ``PreEmissionInputs``, ``PostEmissionInputs`` /
  ``PostEmissionOutputs``, ``BatchFlushInputs`` / ``BatchFlushOutputs``,
  ``BoundaryInputs`` / ``BoundaryOutputs``. Per dispatch site. Every
  bundle is a frozen slots dataclass; container fields are deep-frozen
  in ``__post_init__`` per CLAUDE.md §Frozen Dataclass Immutability.
- ``DeclarationContractViolation`` — per-contract audit-evidence-bearing
  exception. Subclasses declare ``payload_schema`` (H5 Layer 1).
- ``AggregateDeclarationContractViolation`` — SIBLING class (not subclass)
  emitted by the dispatcher when M>1 applicable contracts fire on a single
  (row, call-site) tuple. C5 closure: ``is_aggregate: True`` in the audit
  payload; no ``contract_name`` field (sentinel-string-in-name-column is a
  Spoofing surface per Security S2-001).
- ``ExampleBundle`` — site-tagged return value for ``negative_example`` /
  ``positive_example_does_not_apply``. Lets the harness dispatch per site.

## Audit-complete semantics (comment #417, anchored)

The dispatcher iterates every applicable contract for a given dispatch site.
Each applicable contract's method runs; raised violations are collected
rather than short-circuiting. At loop end: 0 violations → return; 1 →
raise ``violations[0]`` via reference equality (N6 regression invariant);
>=2 → wrap in aggregate, raise. This closes the audit-trail silence that
fail-fast first-fire would have made indistinguishable from "checked and
passed" (STRIDE Repudiation).

## Registry

Contracts register via module-import side-effect. The registry stores each
contract in the global list AND in a per-site map keyed by DispatchSite so
the dispatcher filters in O(1) per site. Registration walks the contract's
class hierarchy for ``@implements_dispatch_site`` markers to compute the
per-site set.

Registry freezes at end of orchestrator bootstrap (see
``freeze_declaration_registry`` + ``prepare_for_run``).
``_clear_registry_for_tests`` / ``_snapshot_registry_for_tests`` /
``_restore_registry_snapshot_for_tests`` are pytest-gated; production
callers raise.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import (
    Any,
    ClassVar,
    Literal,
    NotRequired,
    Required,
    TypedDict,
    TypeVar,
    cast,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from elspeth.contracts.audit_evidence import AuditEvidenceBase
from elspeth.contracts.freeze import deep_freeze, freeze_fields
from elspeth.contracts.secret_scrub import scrub_payload_for_audit
from elspeth.contracts.tier_registry import FrameworkBugError, tier_1_error

# =============================================================================
# DispatchSite — the four named sites (H2 §Fix direction)
# =============================================================================


type DispatchSiteName = Literal[
    "pre_emission_check",
    "post_emission_check",
    "batch_flush_check",
    "boundary_check",
]


class DispatchSite(StrEnum):
    """Named dispatch site. StrEnum so members are directly usable as method
    names via ``getattr(contract, site.value)``."""

    PRE_EMISSION = "pre_emission_check"
    POST_EMISSION = "post_emission_check"
    BATCH_FLUSH = "batch_flush_check"
    BOUNDARY = "boundary_check"


_DISPATCH_SITE_VALUES: frozenset[str] = frozenset(site.value for site in DispatchSite)


# =============================================================================
# @implements_dispatch_site decorator
# =============================================================================


F = TypeVar("F", bound=Callable[..., Any])

# Attribute name carried on decorated methods. The scanner + registry both read
# this. Name is deliberately explicit-and-verbose — an accidental collision with
# another decorator's metadata field would silently mis-classify a method.
_DISPATCH_SITE_MARKER_ATTR: str = "_declaration_dispatch_site"


def implements_dispatch_site(site_name: DispatchSiteName) -> Callable[[F], F]:
    """Mark a method as implementing a named dispatch site.

    Two purposes (H2 §Acceptance AST-detectability + D1 correction):

    1. Runtime: ``register_declaration_contract`` inspects class methods for
       this marker to build the per-site registration map. Methods without
       the marker are NOT invoked by the dispatcher for any site, even if
       their name happens to match a ``DispatchSite`` value.
    2. Static: ``scripts/cicd/enforce_contract_manifest.py`` MC3a/b/c rules
       AST-detect the decorator on concrete contract classes. Required for
       multi-level-inheritance detection per the D1 correction on H2
       (``subclass.__dict__`` does not see mixin-inherited overrides).

    Validates ``site_name`` at decoration time against the DispatchSite enum.
    A typo raises ``ValueError`` at module import rather than silently
    mis-registering.

    CLAUDE.md posture: direct membership check on the frozen set of valid
    values. No ``getattr`` default, no silent pass-through.
    """
    if site_name not in _DISPATCH_SITE_VALUES:
        raise ValueError(
            f"@implements_dispatch_site({site_name!r}) — unknown dispatch site. Must be one of {sorted(_DISPATCH_SITE_VALUES)!r}."
        )

    def wrap(method: F) -> F:
        setattr(method, _DISPATCH_SITE_MARKER_ATTR, site_name)
        return method

    return wrap


# =============================================================================
# Bundle types (per dispatch site, H2 §Fix direction)
# =============================================================================


@dataclass(frozen=True, slots=True)
class PreEmissionInputs:
    """Bundle passed to pre-emission contracts (runs BEFORE transform.process()).

    No ``emitted_rows`` — emission hasn't happened. Pre-emission contracts
    (e.g. ``DeclaredRequiredFieldsContract`` in Phase 2B) validate that
    the input row carries every field the transform's declared_required_fields
    names, before the transform runs and potentially crashes on a missing
    field (which would mis-attribute the failure to the transform's
    ``process()`` body rather than the declaration violation).

    Panel F1 resolution (no ``override_input_fields`` sentinel): the caller
    (``TransformExecutor``) derives ``effective_input_fields`` from
    ``input_row.contract.fields`` once and passes it in. Contracts MUST use
    ``effective_input_fields`` and MUST NOT derive it themselves — the
    caller-side derivation prevents the B-antipattern where each contract
    re-implements the derivation and they drift.

    CLAUDE.md §Frozen Dataclass Immutability: ``frozenset`` is intrinsically
    immutable; no ``__post_init__`` guard required. Scalars need no guard.
    """

    plugin: Any
    node_id: str
    run_id: str
    row_id: str
    token_id: str
    input_row: Any
    static_contract: frozenset[str]
    effective_input_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class PostEmissionInputs:
    """Bundle passed to post-emission contracts (runs AFTER transform.process()).

    Panel F1 resolution: the caller derives ``effective_input_fields`` once
    and passes it in. Contracts reading field semantics use
    ``effective_input_fields`` directly — no ``override_input_fields``
    sentinel. The 2A-era nullable-override field is deleted.
    """

    plugin: Any
    node_id: str
    run_id: str
    row_id: str
    token_id: str
    input_row: Any
    static_contract: frozenset[str]
    effective_input_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class PostEmissionOutputs:
    """Emitted-rows bundle for post-emission dispatch.

    ``emitted_rows`` is normalised to a deep-frozen tuple in ``__post_init__``.
    Non-list/non-tuple inputs crash offensively per CLAUDE.md §Offensive
    Programming — arbitrary Sequence subtypes (lazy wrappers, generators)
    cannot silently bypass the freeze guard.
    """

    emitted_rows: tuple[Any, ...]

    def __post_init__(self) -> None:
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
            raise TypeError(f"PostEmissionOutputs.emitted_rows must be list or tuple, got {type(value).__name__!r}")


@dataclass(frozen=True, slots=True)
class BatchFlushInputs:
    """Bundle for batch-flush dispatch (ADR-009 §Clause 2 TRANSFORM mode).

    Unlike post-emission's single ``input_row``, batch-flush carries a tuple
    of buffered tokens. The identity fields (``row_id``, ``token_id``) anchor
    the violation to the triggering token (or the first buffered token on
    timeout flushes — the caller computes this choice and passes it in).

    ``effective_input_fields`` is the INTERSECTION across every buffered
    token's contract — the weakest shared guarantee. Caller computes this
    once; contracts use it directly.
    """

    plugin: Any
    node_id: str
    run_id: str
    row_id: str  # identity anchor
    token_id: str  # identity anchor
    buffered_tokens: tuple[Any, ...]
    static_contract: frozenset[str]
    effective_input_fields: frozenset[str]

    def __post_init__(self) -> None:
        # buffered_tokens may arrive as list; offensive guard.
        value: object = self.buffered_tokens
        if isinstance(value, list):
            object.__setattr__(self, "buffered_tokens", tuple(value))
        elif isinstance(value, tuple):
            pass  # already canonical — items are TokenInfo dataclasses, considered frozen at the caller.
        else:
            raise TypeError(f"BatchFlushInputs.buffered_tokens must be list or tuple, got {type(value).__name__!r}")


@dataclass(frozen=True, slots=True)
class BatchFlushOutputs:
    """Emitted-rows bundle for batch-flush dispatch. Identical __post_init__
    semantics to PostEmissionOutputs.
    """

    emitted_rows: tuple[Any, ...]

    def __post_init__(self) -> None:
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
            raise TypeError(f"BatchFlushOutputs.emitted_rows must be list or tuple, got {type(value).__name__!r}")


@dataclass(frozen=True, slots=True)
class BoundaryInputs:
    """Bundle for boundary dispatch (source emission / sink consumption — 2C).

    Single ``rows`` tuple whose meaning is context-dependent:
      * source-side adopter: ``rows`` = rows the source produced (plural).
      * sink-side adopter: ``rows`` = rows the sink consumed (plural).

    The contract's ``applies_to`` discriminates source-side vs sink-side
    based on the plugin's concrete class. No singular ``input_row`` —
    sources have none; sinks have plural inputs.

    2C paired-landing (F4) will validate whether this unified bundle is
    sufficient or whether sub-types are needed. Under this H2 landing the
    site + bundle exist so the N1 manifest can record coverage; no 2C
    adopter registers yet.
    """

    plugin: Any
    node_id: str
    run_id: str
    static_contract: frozenset[str]
    rows: tuple[Any, ...]

    def __post_init__(self) -> None:
        value: object = self.rows
        if isinstance(value, list):
            object.__setattr__(self, "rows", tuple(value))
        elif isinstance(value, tuple):
            pass
        else:
            raise TypeError(f"BoundaryInputs.rows must be list or tuple, got {type(value).__name__!r}")


@dataclass(frozen=True, slots=True)
class BoundaryOutputs:
    """Outputs bundle for boundary dispatch.

    For most boundary contracts this is vestigial (sources' emitted rows ARE
    ``BoundaryInputs.rows``; sinks produce nothing). The bundle exists so
    the dispatcher signature ``boundary_check(inputs, outputs)`` matches the
    other three sites structurally. 2C may refine if necessary.
    """

    rows: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        value: object = self.rows
        if isinstance(value, list):
            object.__setattr__(self, "rows", tuple(value))
        elif isinstance(value, tuple):
            pass
        else:
            raise TypeError(f"BoundaryOutputs.rows must be list or tuple, got {type(value).__name__!r}")


# =============================================================================
# ExampleBundle — site-tagged harness example
# =============================================================================


@dataclass(frozen=True, slots=True)
class ExampleBundle:
    """Site-tagged bundle returned by ``negative_example`` /
    ``positive_example_does_not_apply``.

    Under the 4-method ABC the harness cannot know in advance which dispatch
    method to invoke on a given contract. The tagged bundle lets the harness
    dispatch per site:

        bundle = type(contract).negative_example()
        method = getattr(contract, bundle.site.value)
        method(*bundle.args)

    ``args`` shape by site:
      * PRE_EMISSION: ``(PreEmissionInputs,)``
      * POST_EMISSION: ``(PostEmissionInputs, PostEmissionOutputs)``
      * BATCH_FLUSH: ``(BatchFlushInputs, BatchFlushOutputs)``
      * BOUNDARY: ``(BoundaryInputs, BoundaryOutputs)``

    Contracts implementing multiple sites return the bundle for whichever
    site their negative_example primarily exercises. Phase 2B may refine
    if per-site harness coverage needs formalising.
    """

    site: DispatchSite
    args: tuple[Any, ...]


# =============================================================================
# H5 Layer 1 — deny-by-default payload_schema (issue elspeth-3956044fb7)
# =============================================================================
#
# The framework declares ``payload_schema`` on each contract; Layer 1 wires
# that schema onto the violation type so ``__init__`` validates caller-
# supplied payload keys before deep-freeze. The base class's empty default
# means the only legal base-class payload is ``{}`` — concrete violations
# MUST subclass and override ``payload_schema`` with a purpose-built
# TypedDict.
#
# Why this matters: ``scrub_payload_for_audit`` is a closed-set defence and
# cannot cover every secret format that might appear in future contract
# payloads. The deny-by-default gate at construction flips the posture — a
# contract carrying an undeclared key cannot be instantiated, so an unknown
# secret format cannot reach the Landscape audit record.


class _EmptyPayload(TypedDict):
    """Default ``DeclarationContractViolation.payload_schema`` — no keys.

    The only legal payload on the base class is ``{}``. Concrete violations
    MUST subclass ``DeclarationContractViolation`` and override
    ``payload_schema`` with a TypedDict that enumerates every key the
    violation's payload carries.
    """


def _resolve_typeddict_key_sets(schema: type) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(required, optional)`` frozensets for a TypedDict class.

    Implemented via ``typing.get_type_hints(schema, include_extras=True)`` so
    ``NotRequired[...]`` / ``Required[...]`` wrappers survive under
    ``from __future__ import annotations``. The metaclass-populated
    ``__required_keys__`` / ``__optional_keys__`` are unreliable in that
    case because the class-body annotations are string literals the
    metaclass cannot parse at class-definition time. ``get_type_hints``
    resolves the strings at call time and ``typing.get_origin`` yields
    the wrapper so author intent survives regardless of syntax.
    """
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


def resolve_payload_schema_key_sets(schema: type) -> tuple[frozenset[str], frozenset[str]]:
    """Public accessor for payload-schema key classification (N2 Layer B)."""
    return _resolve_typeddict_key_sets(schema)


# =============================================================================
# DeclarationContractViolation — per-contract audit-evidence exception
# =============================================================================


class DeclarationContractViolation(AuditEvidenceBase, RuntimeError):
    """Generic audit-evidence-bearing violation for declaration contracts.

    Individual contracts may subclass to add stronger typing; the base form
    suffices for contracts whose payload is a simple mapping. Subclasses
    MUST override ``payload_schema`` (H5 Layer 1 deny-by-default).

    ``contract_name`` is dispatcher-attributed via ``_attach_contract_name``
    (C4 closure, issue elspeth-d74fe81529). Contracts MUST NOT supply
    ``contract_name`` at construction. ``contract_name`` is exposed as a
    read-only property; ``_attach_contract_name`` is one-shot.
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

    # H5 Layer 1 deny-by-default. Subclasses MUST override.
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
        # H5 Layer 1: validate BEFORE deep-freeze. Cheap offensive guard.
        self._validate_payload_against_schema(payload)
        self._contract_name: str | None = None
        self.plugin = plugin
        self.node_id = node_id
        self.run_id = run_id
        self.row_id = row_id
        self.token_id = token_id
        self.payload: Mapping[str, Any] = deep_freeze(dict(payload))

    @classmethod
    def _validate_payload_against_schema(cls, payload: Mapping[str, Any]) -> None:
        """H5 Layer 1 enforcement — see module docstring."""
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
                f"{sorted(allowed)!r}. Undeclared payload keys could carry "
                f"secret formats the scrubber does not yet recognise — "
                f"declare every key on the violation's payload_schema "
                f"TypedDict (issue elspeth-3956044fb7 / H5 Layer 1)."
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
        """Authoritative contract name attached by the dispatcher (C4)."""
        cn = self._contract_name
        if cn is None:
            raise RuntimeError(
                "DeclarationContractViolation.contract_name accessed before "
                "the dispatcher attached an authoritative name. All "
                "DeclarationContractViolation instances must propagate "
                "through the dispatcher so their contract_name can be "
                "derived from the firing contract's registry entry. "
                "Caller-supplied names were removed to close the spoofing "
                "vector (issue elspeth-d74fe81529 / ADR-010 C4)."
            )
        return cn

    def _attach_contract_name(self, name: str) -> None:
        """One-shot setter for the authoritative contract name (C4)."""
        if self._contract_name is not None:
            raise RuntimeError(
                f"DeclarationContractViolation._attach_contract_name called "
                f"twice: already set to {self._contract_name!r}, refused "
                f"overwrite with {name!r}. The authoritative name is set "
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


# =============================================================================
# AggregateDeclarationContractViolation — N3 primary mitigation (ADR-010 §Semantics)
# =============================================================================


class _AggregatePayload(TypedDict):
    """Payload shape for AggregateDeclarationContractViolation.

    Unlike DCV children which carry a schema-validated ``payload``, the
    aggregate's authoritative structured data IS its ``violations`` tuple
    of child ``to_audit_dict()`` mappings. The payload is minimal — the
    aggregate is a composition, not an independent violation.
    """


@tier_1_error(
    reason="ADR-010 §Semantics — audit-complete dispatch aggregation (N3)",
    caller_module=__name__,
)
class AggregateDeclarationContractViolation(AuditEvidenceBase, RuntimeError):
    """Aggregate wrapper for multi-violation (row, call-site) tuples.

    **SIBLING class of DeclarationContractViolation — NOT a subclass.** Per
    comment #417 §Semantics + N3 §Acceptance C5 closure + Security S2-001.
    A generic ``except DeclarationContractViolation`` elsewhere does NOT
    absorb this; triage SQL must distinguish the aggregate case explicitly.

    Emitted by the dispatcher when M >= 2 applicable contracts fire on a
    single (row, call-site) tuple. Each child's ``to_audit_dict()`` is
    surfaced as an element of the aggregate's ``violations`` list so the
    audit record carries every contract's evidence.

    **Triage SQL:** ``WHERE is_aggregate = true`` distinguishes the
    multi-fire case. The aggregate's ``to_audit_dict`` emits
    ``is_aggregate: True`` and ``violations: tuple[Mapping, ...]``; no
    ``contract_name`` field (sentinel-string-in-name-column is a Spoofing
    surface per S2-001).

    **One-shot dispatcher attribution** (mirrors C4 closure on DCV
    children): ``_attached_by_dispatcher`` flag. The aggregate MUST be
    raised via the dispatcher's audit-complete path; a non-dispatcher
    raise would bypass the audit-completeness invariant.
    """

    __slots__ = ("_attached_by_dispatcher", "plugin", "violations")

    # Payload schema is the empty sentinel — the aggregate has no construction-
    # time validated payload (its payload IS the child-violation tuple). This
    # keeps H5 Layer 1 orthogonal to the aggregate's composition semantics.
    payload_schema: ClassVar[type] = _AggregatePayload

    def __init__(
        self,
        *,
        plugin: str,
        violations: tuple[AuditEvidenceBase, ...],
        message: str,
    ) -> None:
        super().__init__(message)
        if len(violations) < 2:
            raise ValueError(
                "AggregateDeclarationContractViolation requires at least 2 "
                f"violations; got {len(violations)}. Single-violation case "
                f"MUST raise violations[0] via reference equality — the N6 "
                f"regression invariant asserts type(raised) == original and "
                f"id(raised) == id(violations[0]) at N=1, not an "
                f"aggregation-of-one wrapper."
            )
        self._attached_by_dispatcher: bool = False
        self.plugin = plugin
        self.violations = violations  # tuple — immutable by construction

    def _attach_by_dispatcher(self) -> None:
        """One-shot attribution flag. C5 closure mirror of C4's
        ``_attach_contract_name`` on individual DCV instances.
        """
        if self._attached_by_dispatcher:
            raise RuntimeError(
                "AggregateDeclarationContractViolation._attach_by_dispatcher "
                "called twice. The aggregate is raised exactly once per "
                "(row, call-site) tuple by the dispatcher; a second call "
                "indicates a dispatcher bug."
            )
        self._attached_by_dispatcher = True

    def to_audit_dict(self) -> Mapping[str, Any]:
        if not self._attached_by_dispatcher:
            raise RuntimeError(
                "AggregateDeclarationContractViolation.to_audit_dict accessed "
                "before dispatcher attribution. Aggregate was raised outside "
                "the audit-complete dispatcher path — framework bug."
            )
        return {
            "exception_type": type(self).__name__,
            "is_aggregate": True,
            "plugin": self.plugin,
            "violations": tuple(v.to_audit_dict() for v in self.violations),
            "message": str(self),
        }


# =============================================================================
# DeclarationContract — nominal ABC (H2 §Fix direction)
# =============================================================================


class DeclarationContract(ABC):
    """Nominal abstract base for every declaration-trust contract.

    Four dispatch methods carry default no-op bodies. Concrete contracts
    OVERRIDE the methods for sites they implement AND decorate each override
    with ``@implements_dispatch_site("<site>")``. The decorator is the
    authoritative signal; the in-class override is the secondary signal for
    flat (non-mixin) contracts.

    **NOT a runtime-checkable Protocol.** ADR-010 §Alternative 3 rejection
    of structural typing stands: nominal inheritance closes the STRIDE
    Spoofing vector where any class exposing coincidental method signatures
    could claim to be a contract.

    Subclasses MUST:
      * Declare a unique ``name: ClassVar[str]``.
      * Declare a purpose-built ``payload_schema: ClassVar[type]`` (TypedDict).
      * Implement ``applies_to(plugin) -> bool``.
      * Implement ``negative_example(cls) -> ExampleBundle``.
      * Implement ``positive_example_does_not_apply(cls) -> ExampleBundle``.
      * Override at least ONE dispatch method AND decorate it.

    Registration-time enforcement (``register_declaration_contract``) rejects
    contracts with zero implemented sites — a contract that opts into no
    dispatch site is non-functional by construction.
    """

    name: ClassVar[str]
    payload_schema: ClassVar[type]

    @abstractmethod
    def applies_to(self, plugin: Any) -> bool:
        """Return True iff this contract applies to ``plugin``."""

    @classmethod
    @abstractmethod
    def negative_example(cls) -> ExampleBundle:
        """Return a site-tagged scenario that MUST trigger the contract's
        violation when passed to the contract's decorated dispatch method."""

    @classmethod
    @abstractmethod
    def positive_example_does_not_apply(cls) -> ExampleBundle:
        """Return a site-tagged scenario for which ``applies_to`` MUST
        return False (N2 Layer A non-fire invariant)."""

    # -------------------------------------------------------------------------
    # Dispatch methods — default no-op bodies. Concrete contracts override
    # and decorate with @implements_dispatch_site. MC3c CI rule forbids
    # trivial override bodies so opting-in-then-no-op is caught pre-merge.
    # -------------------------------------------------------------------------

    def pre_emission_check(self, inputs: PreEmissionInputs) -> None:
        """Default no-op; decorated override in concrete contracts."""
        return None

    def post_emission_check(
        self,
        inputs: PostEmissionInputs,
        outputs: PostEmissionOutputs,
    ) -> None:
        """Default no-op; decorated override in concrete contracts."""
        return None

    def batch_flush_check(
        self,
        inputs: BatchFlushInputs,
        outputs: BatchFlushOutputs,
    ) -> None:
        """Default no-op; decorated override in concrete contracts."""
        return None

    def boundary_check(
        self,
        inputs: BoundaryInputs,
        outputs: BoundaryOutputs,
    ) -> None:
        """Default no-op; decorated override in concrete contracts."""
        return None


# =============================================================================
# Helpers
# =============================================================================


def derive_effective_input_fields(input_row: Any) -> frozenset[str]:
    """Derive the effective input-field set from a PipelineRow.

    Panel F1 resolution (ADR-010 §Semantics amendment 2026-04-20): callers
    use this single helper so the derivation logic does not drift across
    dispatcher call sites. Contracts receive the derived set in their
    bundle; they do NOT re-derive.

    ``input_row.contract is None`` is a framework invariant violation —
    ``PipelineRow.__init__`` always sets one. Raise ``FrameworkBugError``
    (Tier-1) for the specific "missing contract" case so the error message
    names the root cause explicitly rather than surfacing a generic
    AttributeError from a nested field iteration.
    """
    contract = input_row.contract
    if contract is None:
        raise FrameworkBugError(
            "derive_effective_input_fields: input row has no contract. "
            "PipelineRow.__init__ invariant violated — every row MUST carry "
            "a non-None contract at this dispatcher call site."
        )
    return frozenset(fc.normalized_name for fc in contract.fields)


# =============================================================================
# Registry (H2 extension — per-site map)
# =============================================================================

_REGISTRY: list[DeclarationContract] = []
_REGISTRY_BY_SITE: dict[DispatchSite, list[DeclarationContract]] = {site: [] for site in DispatchSite}
_FROZEN: bool = False


# -----------------------------------------------------------------------------
# EXPECTED_CONTRACT_SITES — extended manifest (N1 Fix direction)
# -----------------------------------------------------------------------------
#
# Per-site manifest: contract_name → frozenset of DispatchSiteName values. The
# orchestrator bootstrap asserts equality between every (name, site) pair
# registered and every (name, site) pair named here. Drift fails loudly.
#
# CLOSED SET — adding or removing a contract requires updating this manifest
# in the SAME commit as the register_declaration_contract(...) call site AND
# the @implements_dispatch_site markers on the contract's methods.
# ``scripts/cicd/enforce_contract_manifest.py`` scans the source tree and
# fails CI if the manifest drifts from the registration + marker call sites.


EXPECTED_CONTRACT_SITES: Mapping[str, frozenset[DispatchSiteName]] = MappingProxyType(
    {
        # PassThroughDeclarationContract
        #   Defined:    src/elspeth/engine/executors/pass_through.py
        #   Registered: src/elspeth/engine/executors/pass_through.py (module-import side-effect)
        #   ADR:        ADR-007 / ADR-008 / ADR-010 (§Semantics amendment 2026-04-20)
        #   Sites:      post_emission_check (single-token TransformExecutor path)
        #               batch_flush_check   (RowProcessor._cross_check_flush_output)
        "passes_through_input": frozenset({"post_emission_check", "batch_flush_check"}),
    }
)


def _collect_contract_sites(contract: DeclarationContract) -> frozenset[DispatchSiteName]:
    """Walk the contract's class hierarchy collecting dispatch-site markers.

    Returns the frozenset of sites the contract implements via
    ``@implements_dispatch_site``. Walks ``type(contract).__mro__`` skipping
    ``object`` and the base ABC so multi-level inheritance (mixins) is
    supported at registration time.

    The MC3 CI rules enforce that the manifest and the marker-discovered set
    agree, so runtime registration and static AST inspection converge on the
    same per-contract site set.
    """
    sites: set[DispatchSiteName] = set()
    for klass in type(contract).__mro__:
        if klass is object or klass is DeclarationContract:
            continue
        for attr_name in vars(klass):
            candidate = vars(klass)[attr_name]
            # Only functions carry the marker; non-callables and dataclass
            # fields are skipped naturally because getattr returns the
            # unwrapped value.
            site_name = getattr(candidate, _DISPATCH_SITE_MARKER_ATTR, None)
            if site_name is None:
                continue
            if site_name not in _DISPATCH_SITE_VALUES:
                raise FrameworkBugError(
                    f"Contract {type(contract).__name__!r} method "
                    f"{attr_name!r} carries @implements_dispatch_site with "
                    f"invalid site {site_name!r}. The decorator validates at "
                    f"decoration time; seeing an invalid marker here "
                    f"indicates bytecode-level tampering or a framework bug."
                )
            sites.add(cast(DispatchSiteName, site_name))
    return frozenset(sites)


def register_declaration_contract(contract: DeclarationContract) -> None:
    """Register a contract. Validates protocol shape, uniqueness, and at
    least one claimed dispatch site.

    Extended (H2) to:
      * Require the contract inherit ``DeclarationContract`` (nominal ABC).
      * Walk the class hierarchy for ``@implements_dispatch_site`` markers.
      * Require at least one claimed site — a contract opting into no site
        is non-functional by construction.
      * Append to ``_REGISTRY_BY_SITE[site]`` for each claimed site AND to
        the global ``_REGISTRY``.

    Raises:
        FrameworkBugError: registry is frozen (post-bootstrap).
        TypeError: contract is not a DeclarationContract subclass; or
            ``payload_schema`` missing / wrong type; or ``negative_example``
            or ``positive_example_does_not_apply`` not callable.
        ValueError: duplicate ``name``; or contract claims zero dispatch
            sites.
    """
    if _FROZEN:
        raise FrameworkBugError(f"Cannot register {contract.name!r}: declaration-contract registry is frozen.")

    if not isinstance(contract, DeclarationContract):
        raise TypeError(
            f"register_declaration_contract requires a DeclarationContract "
            f"subclass instance; got {type(contract).__name__!r}. ADR-010 "
            f"§Alternative 3 rejection of structural Protocol matching "
            f"stands — contracts MUST inherit the nominal ABC."
        )

    # payload_schema validation (H5 Layer 1 — same as 2A).
    try:
        payload_schema = contract.payload_schema
    except AttributeError:
        raise TypeError(f"Contract {contract.name!r} missing required payload_schema attribute") from None
    if not isinstance(payload_schema, type):
        raise TypeError(f"Contract {contract.name!r} payload_schema must be a type (TypedDict subclass)")

    # Example-classmethod callability — N2 Layer A / B harnesses require both.
    for method_name in ("negative_example", "positive_example_does_not_apply"):
        try:
            method = getattr(type(contract), method_name)
        except AttributeError:
            raise TypeError(
                f"Contract {contract.name!r} missing required {method_name!r} classmethod (ADR-010 §Decision 3 + N2 Layer A/B harness)."
            ) from None
        if not callable(method):
            raise TypeError(f"Contract {contract.name!r}.{method_name} must be callable")

    # Claimed-sites validation (H2 §Fix direction + N1 MC3).
    sites = _collect_contract_sites(contract)
    if not sites:
        raise ValueError(
            f"Contract {contract.name!r} claims zero dispatch sites. A "
            f"contract must decorate at least one dispatch method with "
            f'@implements_dispatch_site("<site>") — otherwise the '
            f"dispatcher will never invoke it and the contract is "
            f"non-functional."
        )

    # Uniqueness.
    for existing in _REGISTRY:
        if existing.name == contract.name:
            raise ValueError(f"duplicate contract name {contract.name!r}: already registered")

    _REGISTRY.append(contract)
    for site_name in sites:
        _REGISTRY_BY_SITE[DispatchSite(site_name)].append(contract)


def registered_declaration_contracts() -> Sequence[DeclarationContract]:
    """Return the full contract registry (across all sites)."""
    return tuple(_REGISTRY)


def registered_declaration_contracts_for_site(
    site: DispatchSite,
) -> Sequence[DeclarationContract]:
    """Return contracts that implement ``site`` (marked with the decorator).

    Order preserved from registration order within the site. Used by the
    dispatcher's site-filtered iteration.
    """
    return tuple(_REGISTRY_BY_SITE[site])


def contract_sites(contract: DeclarationContract) -> frozenset[DispatchSiteName]:
    """Return the frozenset of sites ``contract`` implements.

    Exposed for the N1 manifest scanner's runtime fixture pass (MC3a/b).
    """
    return _collect_contract_sites(contract)


def freeze_declaration_registry() -> None:
    """Seal the registry. Called at end of orchestrator bootstrap."""
    global _FROZEN
    _FROZEN = True


def declaration_registry_is_frozen() -> bool:
    """Return whether the registry has been sealed by bootstrap."""
    return _FROZEN


# =============================================================================
# Pytest-gated test helpers (unchanged from 2A — preserved verbatim)
# =============================================================================


def _require_pytest_process(helper_name: str) -> None:
    """Single pytest-process gate for every test-only registry helper."""
    if "pytest" not in sys.modules:
        raise RuntimeError(
            f"{helper_name} called outside a pytest process. This helper "
            "must never run in production — doing so silently disables all "
            "runtime VAL checks. No environment variable or other side-channel "
            "unlock exists: the helper is pytest-gated by design."
        )


def _clear_registry_for_tests() -> None:
    """Test-only: wipe the registry AND reset the freeze flag.

    Clears BOTH the global list AND the per-site map so post-clear
    registration builds the per-site map cleanly.
    """
    global _FROZEN
    _require_pytest_process("_clear_registry_for_tests")
    _REGISTRY.clear()
    for site_list in _REGISTRY_BY_SITE.values():
        site_list.clear()
    _FROZEN = False


def _snapshot_registry_for_tests() -> tuple[
    list[DeclarationContract],
    dict[DispatchSite, list[DeclarationContract]],
    bool,
]:
    """Test-only: snapshot of ``(global_list, per_site_map, frozen_flag)``.

    Extended for the per-site map. The returned ``per_site_map`` is a
    shallow copy of each site's list (lists are mutable; the copy is
    necessary for correct restore semantics).
    """
    _require_pytest_process("_snapshot_registry_for_tests")
    per_site_copy = {site: list(lst) for site, lst in _REGISTRY_BY_SITE.items()}
    return list(_REGISTRY), per_site_copy, _FROZEN


def _restore_registry_snapshot_for_tests(
    snapshot: tuple[
        list[DeclarationContract],
        dict[DispatchSite, list[DeclarationContract]],
        bool,
    ],
) -> None:
    """Test-only: restore from a ``_snapshot_registry_for_tests`` tuple.

    Not safe under concurrent reads (see 2A M2 note preserved verbatim —
    the slice-assignment tightens the teardown window to a single bytecode
    step relative to the prior clear()+extend() pair, but concurrent
    iterators over the registry may still observe an inconsistent state).
    """
    global _FROZEN
    _require_pytest_process("_restore_registry_snapshot_for_tests")
    registry_copy, per_site_copy, frozen_flag = snapshot
    _REGISTRY[:] = registry_copy
    for site, lst in per_site_copy.items():
        _REGISTRY_BY_SITE[site][:] = lst
    _FROZEN = frozen_flag
