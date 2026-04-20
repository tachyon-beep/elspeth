"""BoundaryInputs / boundary dispatcher regression tests for Phase 2C."""

from __future__ import annotations

from typing import Any, ClassVar, TypedDict

import pytest

from elspeth.contracts.declaration_contracts import (
    BoundaryInputs,
    BoundaryOutputs,
    DeclarationContract,
    ExampleBundle,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    implements_dispatch_site,
    register_declaration_contract,
)
from elspeth.engine.executors.declaration_dispatch import run_boundary_checks


class _Payload(TypedDict):
    note: str


class _BoundaryOnlyContract(DeclarationContract):
    name: ClassVar[str] = "boundary_only_test"
    payload_schema: ClassVar[type] = _Payload
    invoked: ClassVar[int] = 0

    def applies_to(self, plugin: Any) -> bool:
        return True

    @implements_dispatch_site("boundary_check")
    def boundary_check(self, inputs: BoundaryInputs, outputs: BoundaryOutputs) -> None:
        type(self).invoked += 1

    @classmethod
    def negative_example(cls) -> ExampleBundle:
        raise NotImplementedError

    @classmethod
    def positive_example_does_not_apply(cls) -> ExampleBundle:
        raise NotImplementedError


class _PostEmissionOnlyContract(DeclarationContract):
    name: ClassVar[str] = "post_only_test"
    payload_schema: ClassVar[type] = _Payload
    invoked: ClassVar[int] = 0

    def applies_to(self, plugin: Any) -> bool:
        return True

    @implements_dispatch_site("post_emission_check")
    def post_emission_check(self, inputs, outputs) -> None:
        type(self).invoked += 1

    @classmethod
    def negative_example(cls) -> ExampleBundle:
        raise NotImplementedError

    @classmethod
    def positive_example_does_not_apply(cls) -> ExampleBundle:
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _isolated_registry():
    snapshot = _snapshot_registry_for_tests()
    _clear_registry_for_tests()
    _BoundaryOnlyContract.invoked = 0
    _PostEmissionOnlyContract.invoked = 0
    yield
    _restore_registry_snapshot_for_tests(snapshot)


def test_boundary_inputs_require_row_identity() -> None:
    with pytest.raises(ValueError, match="row_id must not be empty"):
        BoundaryInputs(
            plugin=object(),
            node_id="node-1",
            run_id="run-1",
            row_id="",
            token_id="token-1",
            static_contract=frozenset(),
            row_data={},
        )

    with pytest.raises(ValueError, match="token_id must not be empty"):
        BoundaryInputs(
            plugin=object(),
            node_id="node-1",
            run_id="run-1",
            row_id="row-1",
            token_id="",
            static_contract=frozenset(),
            row_data={},
        )


def test_run_boundary_checks_dispatches_only_boundary_contracts() -> None:
    register_declaration_contract(_BoundaryOnlyContract())
    register_declaration_contract(_PostEmissionOnlyContract())

    run_boundary_checks(
        inputs=BoundaryInputs(
            plugin=object(),
            node_id="node-1",
            run_id="run-1",
            row_id="row-1",
            token_id="token-1",
            static_contract=frozenset(),
            row_data={"value": 1},
            row_contract=None,
        ),
        outputs=BoundaryOutputs(),
    )

    assert _BoundaryOnlyContract.invoked == 1
    assert _PostEmissionOnlyContract.invoked == 0
