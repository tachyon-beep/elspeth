"""PassThroughDeclarationContract — behaviour parity with direct verify_pass_through.

Also covers the single-token pre-assertions that reviewer B2 flagged as silently
dropped in v0: input-row contract must exist, node_id must be set.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.declaration_contracts import (
    RuntimeCheckInputs,
    RuntimeCheckOutputs,
)
from elspeth.contracts.errors import (
    FrameworkBugError,
    OrchestrationInvariantError,
    PassThroughContractViolation,
)
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.engine.executors.pass_through import PassThroughDeclarationContract


def _contract(fields: tuple[str, ...]) -> SchemaContract:
    return SchemaContract(
        mode="OBSERVED",
        fields=tuple(
            FieldContract(
                normalized_name=n,
                original_name=n,
                python_type=str,
                required=True,
                source="inferred",
                nullable=False,
            )
            for n in fields
        ),
        locked=True,
    )


def _row(fields: tuple[str, ...]) -> PipelineRow:
    return PipelineRow(dict.fromkeys(fields, "v"), _contract(fields))


class _FakeTransform:
    name = "Fake"
    node_id = "n-1"
    passes_through_input = True
    _output_schema_config = None


def test_applies_to_uses_direct_attribute() -> None:
    c = PassThroughDeclarationContract()
    t = _FakeTransform()
    assert c.applies_to(t) is True
    t.passes_through_input = False
    assert c.applies_to(t) is False


def test_applies_to_on_plugin_missing_attribute_crashes() -> None:
    """CLAUDE.md offensive programming: plugin missing passes_through_input is
    a framework bug; must crash loudly, not silently return False."""
    c = PassThroughDeclarationContract()

    class _NoAttr:
        pass

    with pytest.raises(AttributeError):
        c.applies_to(_NoAttr())


def test_runtime_check_raises_on_divergence() -> None:
    c = PassThroughDeclarationContract()
    inputs = RuntimeCheckInputs(
        plugin=_FakeTransform(),
        node_id="n-1",
        run_id="r",
        row_id="rw",
        token_id="t",
        input_row=_row(("a", "b", "c")),
        static_contract=frozenset({"a", "b", "c"}),
    )
    outputs = RuntimeCheckOutputs(emitted_rows=(_row(("a", "c")),))
    with pytest.raises(PassThroughContractViolation) as exc_info:
        c.runtime_check(inputs, outputs)
    assert exc_info.value.divergence_set == frozenset({"b"})


def test_runtime_check_empty_emission_is_noop() -> None:
    c = PassThroughDeclarationContract()
    inputs = RuntimeCheckInputs(
        plugin=_FakeTransform(),
        node_id="n-1",
        run_id="r",
        row_id="rw",
        token_id="t",
        input_row=_row(("a",)),
        static_contract=frozenset(),
    )
    c.runtime_check(inputs, RuntimeCheckOutputs(emitted_rows=()))


def test_runtime_check_preserves_frameworkbugerror_on_missing_contract() -> None:
    """B2 regression: input_row without contract must raise FrameworkBugError."""
    c = PassThroughDeclarationContract()

    class _BadRow:
        contract = None

    inputs = RuntimeCheckInputs(
        plugin=_FakeTransform(),
        node_id="n-1",
        run_id="r",
        row_id="rw",
        token_id="t",
        input_row=_BadRow(),
        static_contract=frozenset(),
    )
    with pytest.raises(FrameworkBugError):
        c.runtime_check(inputs, RuntimeCheckOutputs(emitted_rows=(_row(("a",)),)))


def test_runtime_check_preserves_orchestrationinvarianterror_on_missing_node_id() -> None:
    """B2 regression: transform.node_id=None must raise OrchestrationInvariantError."""
    c = PassThroughDeclarationContract()
    plugin = _FakeTransform()
    plugin.node_id = None
    inputs = RuntimeCheckInputs(
        plugin=plugin,
        node_id="",
        run_id="r",
        row_id="rw",
        token_id="t",
        input_row=_row(("a",)),
        static_contract=frozenset(),
    )
    with pytest.raises(OrchestrationInvariantError):
        c.runtime_check(inputs, RuntimeCheckOutputs(emitted_rows=(_row(("a",)),)))


def test_negative_example_fires_violation() -> None:
    c = PassThroughDeclarationContract()
    inputs, outputs = c.negative_example()
    with pytest.raises(PassThroughContractViolation):
        c.runtime_check(inputs, outputs)
