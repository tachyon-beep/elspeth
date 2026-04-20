"""Framework-extensibility proof: a real-shape ``CreatesTokensContract`` fits in
the ADR-010 registry without structural changes (Track 2 Phase 2A, Task 11).

Reviewer B10 rationale: the proof contract uses the actual ``creates_tokens``
attribute that already lives on ``BaseTransform`` (not a synthetic boolean), so
the 4 tests below are VAL evidence ("Phase 2B can fit in ≤200 LOC") rather than
mere VER ("the registry iterates something").

Registry isolation uses the Task 7 snapshot/restore API so this file's
side-effects never leak into sibling invariant tests.
"""

from __future__ import annotations

from typing import Any, TypedDict

import pytest

import elspeth.engine.executors.pass_through  # noqa: F401  — side-effect: registers PassThroughDeclarationContract
from elspeth.contracts.audit_evidence import AuditEvidenceBase
from elspeth.contracts.declaration_contracts import (
    DeclarationContract,
    DeclarationContractViolation,
    DispatchSite,
    ExampleBundle,
    PostEmissionInputs,
    PostEmissionOutputs,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    implements_dispatch_site,
    register_declaration_contract,
    registered_declaration_contracts,
)
from elspeth.engine.executors.declaration_dispatch import run_post_emission_checks

# ---------------------------------------------------------------------------
# CreatesTokensViolation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Payload schema (TypedDict — required by DeclarationContract protocol and by
# H5 Layer 1 deny-by-default violation construction)
# ---------------------------------------------------------------------------


class CreatesTokensPayload(TypedDict):
    creates_tokens: bool
    emitted_count: int


class CreatesTokensViolation(DeclarationContractViolation):
    """Raised when a creates_tokens=True transform emits only one row.

    A transform annotated creates_tokens=True is declaring it will produce
    multiple child tokens via deaggregation. Emitting a single row is a
    contract violation: either the annotation is wrong or the transform
    failed to expand.

    H5 Layer 1: ``payload_schema`` matches ``CreatesTokensContract.payload_schema``
    so construction-time validation rejects unknown keys on this violation's
    ``payload`` kwarg.
    """

    payload_schema = CreatesTokensPayload


# ---------------------------------------------------------------------------
# CreatesTokensContract (real-shape Phase-2B candidate)
# ---------------------------------------------------------------------------


class CreatesTokensContract(DeclarationContract):
    """Declaration contract for transforms that set ``creates_tokens=True``.

    ``applies_to`` uses try/except AttributeError rather than hasattr (banned
    by CLAUDE.md). Post-H2 inherits the nominal ABC and decorates its
    post-emission dispatch method with ``@implements_dispatch_site``.
    """

    name = "creates_tokens"
    payload_schema: type = CreatesTokensPayload

    def applies_to(self, plugin: Any) -> bool:
        try:
            flag = plugin.creates_tokens
        except AttributeError:
            return False
        return bool(flag)

    @implements_dispatch_site("post_emission_check")
    def post_emission_check(self, inputs: PostEmissionInputs, outputs: PostEmissionOutputs) -> None:
        """Verify that a creates_tokens=True transform emitted more than one row.

        A single-row emission from a creates_tokens=True transform indicates
        either a mis-annotation or a deaggregation that silently collapsed —
        both are reportable contract violations.

        Direct attribute access — plugin.creates_tokens must exist if
        applies_to returned True for this plugin.
        """
        creates_tokens_flag: bool = inputs.plugin.creates_tokens
        emitted_count = len(outputs.emitted_rows)

        if creates_tokens_flag and emitted_count == 1:
            # C4: contract_name is attached by the dispatcher; the contract's
            # own runtime_check MUST NOT supply it. (Previously the proof
            # contract passed ``contract_name=self.name`` — the whole point
            # of the C4 closure is that contracts cannot self-label.)
            raise CreatesTokensViolation(
                plugin=inputs.plugin.name,
                node_id=inputs.node_id,
                run_id=inputs.run_id,
                row_id=inputs.row_id,
                token_id=inputs.token_id,
                payload={
                    "creates_tokens": creates_tokens_flag,
                    "emitted_count": emitted_count,
                },
                message=(
                    f"Transform {inputs.plugin.name!r} (node {inputs.node_id!r}) "
                    f"declared creates_tokens=True but emitted exactly 1 row — "
                    f"expected a multi-row deaggregation expansion."
                ),
            )

    @classmethod
    def negative_example(cls) -> ExampleBundle:
        """A creates_tokens=True plugin that emits exactly 1 row — must raise."""

        class _MinimalCreatesTokensTransform:
            name = "NegativeCreatesTokensExample"
            node_id = "ct-neg-1"
            creates_tokens = True

        inputs = PostEmissionInputs(
            plugin=_MinimalCreatesTokensTransform(),
            node_id="ct-neg-1",
            run_id="ct-neg-run",
            row_id="ct-neg-row",
            token_id="ct-neg-token",
            input_row=object(),
            static_contract=frozenset(),
            effective_input_fields=frozenset(),
        )
        outputs = PostEmissionOutputs(emitted_rows=(object(),))
        return ExampleBundle(site=DispatchSite.POST_EMISSION, args=(inputs, outputs))

    @classmethod
    def positive_example_does_not_apply(cls) -> ExampleBundle:
        """A creates_tokens=False plugin — applies_to must return False."""

        class _NonCreatesTokensTransform:
            name = "NonFireCreatesTokensExample"
            node_id = "ct-non-fire-1"
            creates_tokens = False

        inputs = PostEmissionInputs(
            plugin=_NonCreatesTokensTransform(),
            node_id="ct-non-fire-1",
            run_id="ct-non-fire-run",
            row_id="ct-non-fire-row",
            token_id="ct-non-fire-token",
            input_row=object(),
            static_contract=frozenset(),
            effective_input_fields=frozenset(),
        )
        outputs = PostEmissionOutputs(emitted_rows=(object(), object(), object()))
        return ExampleBundle(site=DispatchSite.POST_EMISSION, args=(inputs, outputs))


# ---------------------------------------------------------------------------
# Fixture: snapshot-and-restore so the proof contract does not leak
# ---------------------------------------------------------------------------


@pytest.fixture
def proof_contract_registered() -> Any:
    """Snapshot the registry, register CreatesTokensContract, yield, restore.

    Uses the Task 7 snapshot/restore API. After the snapshot is taken we call
    _clear_registry_for_tests() (which also unfreezes) and re-import the
    pass_through module side-effect to re-register PassThroughDeclarationContract
    before adding the proof contract. On teardown the snapshot is restored so
    subsequent tests in the suite see the original registry state.
    """
    snapshot = _snapshot_registry_for_tests()
    # Wipe + unfreeze so we can register fresh contracts without hitting the
    # frozen-registry guard.
    _clear_registry_for_tests()
    # Re-register PassThrough so the registry is never left empty.
    # The module-level side-effect fires only once per process; we call
    # register_declaration_contract directly to re-add the contract.
    from elspeth.engine.executors.pass_through import PassThroughDeclarationContract

    register_declaration_contract(PassThroughDeclarationContract())
    c = CreatesTokensContract()
    register_declaration_contract(c)
    yield c
    _restore_registry_snapshot_for_tests(snapshot)


# ---------------------------------------------------------------------------
# Test 1: Registry admission
# ---------------------------------------------------------------------------


def test_registry_admits_creates_tokens_proof(proof_contract_registered: Any) -> None:
    """``CreatesTokensContract`` registers without error and appears in the
    registry under its declared name.

    VAL evidence: the ADR-010 framework's registry validation (uniqueness,
    payload_schema, negative_example callability) all pass for a real-shape
    Phase 2B contract body.
    """
    names = {c.name for c in registered_declaration_contracts()}
    assert proof_contract_registered.name in names, f"Expected 'creates_tokens' in registry; found {sorted(names)!r}"


# ---------------------------------------------------------------------------
# Test 2: Dispatcher invocation (no-raise path)
# ---------------------------------------------------------------------------


def test_dispatcher_invokes_creates_tokens_proof(proof_contract_registered: Any) -> None:
    """``run_post_emission_checks`` invokes ``CreatesTokensContract.post_emission_check``
    when the plugin has ``creates_tokens=True`` and emits >1 row (happy path).

    The dispatcher must NOT raise for a compliant plugin.
    """

    class _CompliantTransform:
        name = "CompliantCreatesTokens"
        node_id = "ct-ok-1"
        creates_tokens = True
        # PassThroughDeclarationContract.applies_to accesses this directly
        # (no getattr default). The stub must carry every attribute that
        # registered contracts' applies_to may read.
        passes_through_input = False

    inputs = PostEmissionInputs(
        plugin=_CompliantTransform(),
        node_id="ct-ok-1",
        run_id="disp-run",
        row_id="disp-row",
        token_id="disp-token",
        input_row=object(),
        static_contract=frozenset(),
        effective_input_fields=frozenset(),
    )
    outputs = PostEmissionOutputs(emitted_rows=(object(), object()))

    # Must not raise — happy path.
    run_post_emission_checks(inputs=inputs, outputs=outputs)


# ---------------------------------------------------------------------------
# Test 3: AuditEvidence compatibility
# ---------------------------------------------------------------------------


def test_creates_tokens_violation_is_audit_evidence(
    proof_contract_registered: Any,
) -> None:
    """``CreatesTokensViolation`` inherits ``AuditEvidenceBase`` and its
    ``to_audit_dict()`` output contains the required keys.

    Verifies the violation integrates with the Landscape audit trail without
    requiring engine infrastructure (unit-scope proof).
    """
    violation = CreatesTokensViolation(
        plugin="TestTransform",
        node_id="ct-node",
        run_id="ct-run",
        row_id="ct-row",
        token_id="ct-token",
        payload={"creates_tokens": True, "emitted_count": 1},
        message="proof violation",
    )
    # Simulate dispatcher-attached contract_name (the C4 closure makes this
    # the only attribution path).
    violation._attach_contract_name("creates_tokens")

    assert isinstance(violation, AuditEvidenceBase), "CreatesTokensViolation must inherit AuditEvidenceBase to integrate with Landscape."
    assert isinstance(violation, DeclarationContractViolation), "CreatesTokensViolation must be a DeclarationContractViolation subclass."

    audit = violation.to_audit_dict()
    required_keys = {
        "exception_type",
        "contract_name",
        "plugin",
        "node_id",
        "run_id",
        "row_id",
        "token_id",
        "payload",
        "message",
    }
    missing = required_keys - set(audit.keys())
    assert not missing, f"to_audit_dict() missing keys: {sorted(missing)!r}"

    assert audit["exception_type"] == "CreatesTokensViolation"
    assert audit["contract_name"] == "creates_tokens"
    assert audit["payload"]["creates_tokens"] is True
    assert audit["payload"]["emitted_count"] == 1


# ---------------------------------------------------------------------------
# Test 4: Negative example fires violation
# ---------------------------------------------------------------------------


def test_negative_example_fires_violation(proof_contract_registered: Any) -> None:
    """``CreatesTokensContract.negative_example()`` produces inputs that cause
    ``runtime_check`` to raise ``CreatesTokensViolation``.

    Mirrors the ``test_contract_negative_examples_fire.py`` pattern: every
    registered contract's negative_example must trigger a violation, otherwise
    the runtime VAL check is dormant. This test applies the same invariant to
    the proof contract explicitly.
    """
    contract = proof_contract_registered
    bundle = type(contract).negative_example()
    method = getattr(contract, bundle.site.value)

    with pytest.raises(CreatesTokensViolation) as exc_info:
        method(*bundle.args)

    assert exc_info.value is not None
    assert isinstance(exc_info.value, DeclarationContractViolation), (
        "CreatesTokensViolation must be catchable as DeclarationContractViolation."
    )
    assert isinstance(exc_info.value, AuditEvidenceBase), "CreatesTokensViolation must be AuditEvidenceBase so Landscape can record it."
