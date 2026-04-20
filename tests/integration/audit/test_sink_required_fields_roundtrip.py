"""SinkRequiredFieldsContract -> dispatcher -> Landscape -> explain() round-trip."""

from __future__ import annotations

import json
from typing import Any, ClassVar, TypedDict

from elspeth.contracts import NodeStateFailed, NodeType
from elspeth.contracts.declaration_contracts import (
    AggregateDeclarationContractViolation,
    BoundaryInputs,
    BoundaryOutputs,
    DeclarationContract,
    DeclarationContractViolation,
    ExampleBundle,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    implements_dispatch_site,
    register_declaration_contract,
)
from elspeth.contracts.enums import NodeStateStatus
from elspeth.contracts.errors import ExecutionError, SinkRequiredFieldsViolation
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape.lineage import explain
from elspeth.engine.executors.declaration_dispatch import run_boundary_checks
from elspeth.engine.executors.sink_required_fields import SinkRequiredFieldsContract
from tests.fixtures.landscape import make_recorder_with_run, register_test_node


def _setup_landscape(*, run_id: str, row_id: str, token_id: str, node_id: str):
    setup = make_recorder_with_run(
        run_id=run_id,
        source_node_id="source-0",
        source_plugin_name="test-source",
    )
    register_test_node(
        setup.factory.data_flow,
        run_id=run_id,
        node_id=node_id,
        node_type=NodeType.SINK,
        plugin_name="SinkRequiredFieldsSink",
    )
    row = setup.factory.data_flow.create_row(
        run_id=run_id,
        source_node_id="source-0",
        row_index=0,
        data={"customer_id": "v"},
        row_id=row_id,
    )
    setup.factory.data_flow.create_token(row_id=row.row_id, token_id=token_id)
    return setup


def _record_failure(setup, *, token_id: str, node_id: str, run_id: str, error: ExecutionError) -> dict[str, Any]:
    state = setup.factory.execution.begin_node_state(
        token_id=token_id,
        node_id=node_id,
        run_id=run_id,
        step_index=1,
        input_data={"customer_id": "v"},
    )
    setup.factory.execution.complete_node_state(
        state.state_id,
        NodeStateStatus.FAILED,
        duration_ms=0.0,
        error=error,
    )

    lineage = explain(
        query=setup.factory.query,
        data_flow=setup.factory.data_flow,
        run_id=run_id,
        token_id=token_id,
    )
    assert lineage is not None
    failed_states = [ns for ns in lineage.node_states if isinstance(ns, NodeStateFailed)]
    assert len(failed_states) == 1
    assert failed_states[0].error_json is not None
    return json.loads(failed_states[0].error_json)["context"]


def _contract(
    *,
    required_fields: tuple[str, ...],
    optional_fields: tuple[str, ...] = (),
) -> SchemaContract:
    fields = tuple(
        FieldContract(
            normalized_name=name,
            original_name=name,
            python_type=str,
            required=True,
            source="inferred",
            nullable=False,
        )
        for name in required_fields
    ) + tuple(
        FieldContract(
            normalized_name=name,
            original_name=name,
            python_type=str,
            required=False,
            source="inferred",
            nullable=False,
        )
        for name in optional_fields
    )
    return SchemaContract(mode="OBSERVED", fields=fields, locked=True)


def _plugin(
    *,
    name: str = "SinkRequiredFieldsSink",
    node_id: str = "sink-required-fields-node",
    declared_required_fields: frozenset[str] = frozenset({"customer_id", "amount"}),
) -> Any:
    plugin = type("SinkRequiredFieldsPlugin", (), {})()
    plugin.name = name
    plugin.node_id = node_id
    plugin.declared_required_fields = declared_required_fields
    return plugin


class _SecondaryPayload(TypedDict):
    note: str


class _SecondaryBoundaryViolation(DeclarationContractViolation):
    payload_schema = _SecondaryPayload


class _SecondaryBoundaryContract(DeclarationContract):
    name: ClassVar[str] = "secondary_sink_boundary_test"
    payload_schema: ClassVar[type] = _SecondaryPayload

    def applies_to(self, plugin: Any) -> bool:
        return bool(plugin.declared_required_fields)

    @implements_dispatch_site("boundary_check")
    def boundary_check(self, inputs: BoundaryInputs, outputs: BoundaryOutputs) -> None:
        raise _SecondaryBoundaryViolation(
            plugin=inputs.plugin.name,
            node_id=inputs.node_id,
            run_id=inputs.run_id,
            row_id=inputs.row_id,
            token_id=inputs.token_id,
            payload={"note": "second"},
            message="secondary sink boundary violation",
        )

    @classmethod
    def negative_example(cls) -> ExampleBundle:
        raise NotImplementedError

    @classmethod
    def positive_example_does_not_apply(cls) -> ExampleBundle:
        raise NotImplementedError


class TestSinkRequiredFieldsRoundTrip:
    def setup_method(self) -> None:
        self._snapshot = _snapshot_registry_for_tests()
        _clear_registry_for_tests()

    def teardown_method(self) -> None:
        _restore_registry_snapshot_for_tests(self._snapshot)

    def test_boundary_violation_survives_landscape_round_trip(self) -> None:
        register_declaration_contract(SinkRequiredFieldsContract())

        run_id = "run-sink-required-fields"
        row_id = "row-sink-required-fields"
        token_id = "token-sink-required-fields"
        node_id = "sink-required-fields-node"
        setup = _setup_landscape(run_id=run_id, row_id=row_id, token_id=token_id, node_id=node_id)

        try:
            run_boundary_checks(
                inputs=BoundaryInputs(
                    plugin=_plugin(node_id=node_id),
                    node_id=node_id,
                    run_id=run_id,
                    row_id=row_id,
                    token_id=token_id,
                    static_contract=frozenset({"customer_id", "amount"}),
                    row_data={"customer_id": "v"},
                    row_contract=_contract(required_fields=("customer_id",), optional_fields=("amount",)),
                ),
                outputs=BoundaryOutputs(),
            )
        except SinkRequiredFieldsViolation as violation:
            error = ExecutionError(
                exception=str(violation),
                exception_type=type(violation).__name__,
                phase="sink_write",
                context=violation.to_audit_dict(),
            )
        else:
            raise AssertionError("Expected SinkRequiredFieldsViolation")

        context = _record_failure(setup, token_id=token_id, node_id=node_id, run_id=run_id, error=error)
        assert context["exception_type"] == "SinkRequiredFieldsViolation"
        assert context["contract_name"] == "sink_required_fields"
        assert context["plugin"] == "SinkRequiredFieldsSink"
        assert context["node_id"] == node_id
        assert context["run_id"] == run_id
        assert context["row_id"] == row_id
        assert context["token_id"] == token_id
        assert context["payload"]["declared"] == ["amount", "customer_id"]
        assert context["payload"]["runtime_observed"] == ["customer_id"]
        assert context["payload"]["missing"] == ["amount"]

    def test_aggregate_round_trip_with_second_boundary_contract(self) -> None:
        register_declaration_contract(SinkRequiredFieldsContract())
        register_declaration_contract(_SecondaryBoundaryContract())

        run_id = "run-sink-required-fields-aggregate"
        row_id = "row-sink-required-fields-aggregate"
        token_id = "token-sink-required-fields-aggregate"
        node_id = "sink-required-fields-node"
        setup = _setup_landscape(run_id=run_id, row_id=row_id, token_id=token_id, node_id=node_id)

        try:
            run_boundary_checks(
                inputs=BoundaryInputs(
                    plugin=_plugin(node_id=node_id),
                    node_id=node_id,
                    run_id=run_id,
                    row_id=row_id,
                    token_id=token_id,
                    static_contract=frozenset({"customer_id", "amount"}),
                    row_data={"customer_id": "v"},
                    row_contract=None,
                ),
                outputs=BoundaryOutputs(),
            )
        except AggregateDeclarationContractViolation as aggregate:
            error = ExecutionError(
                exception=str(aggregate),
                exception_type=type(aggregate).__name__,
                phase="sink_write",
                context=aggregate.to_audit_dict(),
            )
        else:
            raise AssertionError("Expected AggregateDeclarationContractViolation")

        context = _record_failure(setup, token_id=token_id, node_id=node_id, run_id=run_id, error=error)
        assert context["exception_type"] == "AggregateDeclarationContractViolation"
        assert context["is_aggregate"] is True
        child_types = {entry["exception_type"] for entry in context["violations"]}
        assert child_types == {"SinkRequiredFieldsViolation", "_SecondaryBoundaryViolation"}
