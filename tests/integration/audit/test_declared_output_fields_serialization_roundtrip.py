"""DeclaredOutputFieldsContract -> dispatcher -> Landscape -> explain() round-trip."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from elspeth.contracts import NodeStateFailed, NodeType
from elspeth.contracts.declaration_contracts import (
    AggregateDeclarationContractViolation,
    BatchFlushInputs,
    BatchFlushOutputs,
    DeclarationContractViolation,
    PostEmissionInputs,
    PostEmissionOutputs,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    register_declaration_contract,
)
from elspeth.contracts.enums import NodeStateStatus
from elspeth.contracts.errors import DeclaredOutputFieldsViolation, ExecutionError
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.core.landscape.lineage import explain
from elspeth.engine.executors.declaration_dispatch import (
    run_batch_flush_checks,
    run_post_emission_checks,
)
from elspeth.engine.executors.declared_output_fields import DeclaredOutputFieldsContract
from elspeth.engine.executors.pass_through import PassThroughDeclarationContract
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
        node_type=NodeType.TRANSFORM,
        plugin_name="DeclaredOutputFieldsTransform",
    )
    row = setup.factory.data_flow.create_row(
        run_id=run_id,
        source_node_id="source-0",
        row_index=0,
        data={"source": "v"},
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
        input_data={"source": "v"},
    )
    setup.factory.execution.complete_node_state(
        state.state_id,
        NodeStateStatus.FAILED,
        duration_ms=1.0,
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


def _contract(fields: tuple[str, ...]) -> SchemaContract:
    return SchemaContract(
        mode="OBSERVED",
        fields=tuple(
            FieldContract(
                normalized_name=name,
                original_name=name,
                python_type=str,
                required=True,
                source="inferred",
                nullable=False,
            )
            for name in fields
        ),
        locked=True,
    )


def _row(fields: tuple[str, ...]) -> PipelineRow:
    return PipelineRow(dict.fromkeys(fields, "v"), _contract(fields))


def _plugin(
    *,
    name: str = "DeclaredOutputFieldsTransform",
    node_id: str = "declared-output-fields-node",
    declared_output_fields: frozenset[str] = frozenset({"new_a", "new_b"}),
    passes_through_input: bool = False,
    can_drop_rows: bool = False,
    declared_input_fields: frozenset[str] = frozenset(),
    is_batch_aware: bool = False,
) -> Any:
    plugin = type("DeclaredOutputFieldsPlugin", (), {})()
    plugin.name = name
    plugin.node_id = node_id
    plugin.declared_output_fields = declared_output_fields
    plugin.passes_through_input = passes_through_input
    plugin.can_drop_rows = can_drop_rows
    plugin.declared_input_fields = declared_input_fields
    plugin.is_batch_aware = is_batch_aware
    plugin._output_schema_config = None
    return plugin


class _SecretPayload(TypedDict):
    marker: str


class _SecretRoundTripViolation(DeclarationContractViolation):
    payload_schema = _SecretPayload


class TestDeclaredOutputFieldsRoundTrip:
    def setup_method(self) -> None:
        self._snapshot = _snapshot_registry_for_tests()
        _clear_registry_for_tests()

    def teardown_method(self) -> None:
        _restore_registry_snapshot_for_tests(self._snapshot)

    def test_post_emission_violation_survives_landscape_round_trip(self) -> None:
        register_declaration_contract(DeclaredOutputFieldsContract())

        run_id = "run-declared-output-fields"
        row_id = "row-declared-output-fields"
        token_id = "token-declared-output-fields"
        node_id = "node-declared-output-fields"
        setup = _setup_landscape(run_id=run_id, row_id=row_id, token_id=token_id, node_id=node_id)

        plugin = _plugin(node_id=node_id)
        inputs = PostEmissionInputs(
            plugin=plugin,
            node_id=node_id,
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            input_row=_row(("source",)),
            static_contract=frozenset({"new_a", "new_b"}),
            effective_input_fields=frozenset({"source"}),
        )
        outputs = PostEmissionOutputs(emitted_rows=(_row(("source", "new_a")),))

        try:
            run_post_emission_checks(inputs=inputs, outputs=outputs)
        except DeclaredOutputFieldsViolation as violation:
            error = ExecutionError(
                exception=str(violation),
                exception_type=type(violation).__name__,
                phase="executor_post_process",
                context=violation.to_audit_dict(),
            )
        else:
            raise AssertionError("Expected DeclaredOutputFieldsViolation")

        context = _record_failure(setup, token_id=token_id, node_id=node_id, run_id=run_id, error=error)
        assert context["exception_type"] == "DeclaredOutputFieldsViolation"
        assert context["contract_name"] == "declared_output_fields"
        assert context["plugin"] == "DeclaredOutputFieldsTransform"
        assert context["node_id"] == node_id
        assert context["run_id"] == run_id
        assert context["row_id"] == row_id
        assert context["token_id"] == token_id
        assert context["payload"]["declared"] == ["new_a", "new_b"]
        assert context["payload"]["runtime_observed"] == ["new_a", "source"]
        assert context["payload"]["missing"] == ["new_b"]

    def test_batch_flush_violation_survives_landscape_round_trip(self) -> None:
        register_declaration_contract(DeclaredOutputFieldsContract())

        run_id = "run-declared-output-fields-batch"
        row_id = "row-declared-output-fields-batch"
        token_id = "token-declared-output-fields-batch"
        node_id = "node-declared-output-fields-batch"
        setup = _setup_landscape(run_id=run_id, row_id=row_id, token_id=token_id, node_id=node_id)

        plugin = _plugin(node_id=node_id)
        token_row = _row(("source",))
        inputs = BatchFlushInputs(
            plugin=plugin,
            node_id=node_id,
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            buffered_tokens=(token_row,),
            static_contract=frozenset({"new_a", "new_b"}),
            effective_input_fields=frozenset({"source"}),
        )
        outputs = BatchFlushOutputs(emitted_rows=(_row(("source", "new_a")),))

        try:
            run_batch_flush_checks(inputs=inputs, outputs=outputs)
        except DeclaredOutputFieldsViolation as violation:
            error = ExecutionError(
                exception=str(violation),
                exception_type=type(violation).__name__,
                phase="batch_flush_dispatch",
                context=violation.to_audit_dict(),
            )
        else:
            raise AssertionError("Expected DeclaredOutputFieldsViolation on batch-flush path")

        context = _record_failure(setup, token_id=token_id, node_id=node_id, run_id=run_id, error=error)
        assert context["exception_type"] == "DeclaredOutputFieldsViolation"
        assert context["contract_name"] == "declared_output_fields"
        assert context["payload"]["missing"] == ["new_b"]

    def test_aggregate_round_trip_with_pass_through(self) -> None:
        register_declaration_contract(PassThroughDeclarationContract())
        register_declaration_contract(DeclaredOutputFieldsContract())

        run_id = "run-declared-output-fields-aggregate"
        row_id = "row-declared-output-fields-aggregate"
        token_id = "token-declared-output-fields-aggregate"
        node_id = "node-declared-output-fields-aggregate"
        setup = _setup_landscape(run_id=run_id, row_id=row_id, token_id=token_id, node_id=node_id)

        plugin = _plugin(node_id=node_id, passes_through_input=True)
        input_row = _row(("source", "carry"))
        inputs = PostEmissionInputs(
            plugin=plugin,
            node_id=node_id,
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            input_row=input_row,
            static_contract=frozenset({"new_a", "new_b"}),
            effective_input_fields=frozenset({"source", "carry"}),
        )
        outputs = PostEmissionOutputs(emitted_rows=(_row(("source", "new_a")),))

        try:
            run_post_emission_checks(inputs=inputs, outputs=outputs)
        except AggregateDeclarationContractViolation as aggregate:
            error = ExecutionError(
                exception=str(aggregate),
                exception_type=type(aggregate).__name__,
                phase="executor_post_process",
                context=aggregate.to_audit_dict(),
            )
        else:
            raise AssertionError("Expected AggregateDeclarationContractViolation")

        context = _record_failure(setup, token_id=token_id, node_id=node_id, run_id=run_id, error=error)
        assert context["exception_type"] == "AggregateDeclarationContractViolation"
        assert context["is_aggregate"] is True
        child_types = {entry["exception_type"] for entry in context["violations"]}
        assert child_types == {"DeclaredOutputFieldsViolation", "PassThroughContractViolation"}
        declared_child = next(entry for entry in context["violations"] if entry["exception_type"] == "DeclaredOutputFieldsViolation")
        assert declared_child["contract_name"] == "declared_output_fields"
        assert declared_child["payload"]["missing"] == ["new_b"]

        pass_through_child = next(entry for entry in context["violations"] if entry["exception_type"] == "PassThroughContractViolation")
        assert pass_through_child["divergence_set"] == ["carry"]

    def test_secret_like_payload_value_is_scrubbed_before_landscape_round_trip(self) -> None:
        run_id = "run-declared-output-fields-secret"
        row_id = "row-declared-output-fields-secret"
        token_id = "token-declared-output-fields-secret"
        node_id = "node-declared-output-fields"
        setup = _setup_landscape(run_id=run_id, row_id=row_id, token_id=token_id, node_id=node_id)

        violation = _SecretRoundTripViolation(
            plugin="DeclaredOutputFieldsTransform",
            node_id=node_id,
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            payload={"marker": "sk-abcdef1234567890abcdef1234567890"},
            message="secret round-trip test",
        )
        violation._attach_contract_name("declared_output_fields_secret_roundtrip")

        error = ExecutionError(
            exception=str(violation),
            exception_type=type(violation).__name__,
            phase="executor_post_process",
            context=violation.to_audit_dict(),
        )

        context = _record_failure(setup, token_id=token_id, node_id=node_id, run_id=run_id, error=error)
        assert "sk-abcdef" not in json.dumps(context)
        assert context["payload"]["marker"] == "<redacted-secret>"
