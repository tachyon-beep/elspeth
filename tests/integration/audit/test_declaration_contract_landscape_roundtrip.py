"""DeclarationContractViolation -> Landscape -> explain() round-trip.

CLAUDE.md attributability mandate: for any output, explain(recorder, run_id,
token_id) must prove complete lineage. This test exercises the generic violation
shape end-to-end so the Landscape schema compatibility is proven before any
Phase 2B contract relies on it (ADR-010 reviewer B16).

Pattern: direct ExecutionRepository API calls (begin_node_state +
complete_node_state) rather than full engine setup, mirroring how the
pass-through test calls processor internals directly. The NodeStateGuard
path that wires AuditEvidenceBase.to_audit_dict() into ExecutionError.context
is exercised via the same code path the engine uses at runtime.
"""

from __future__ import annotations

import json

from elspeth.contracts import NodeStateFailed, NodeType
from elspeth.contracts.declaration_contracts import DeclarationContractViolation
from elspeth.contracts.enums import NodeStateStatus
from elspeth.contracts.errors import ExecutionError
from elspeth.core.landscape.lineage import explain
from tests.fixtures.landscape import make_recorder_with_run, register_test_node


def _setup_landscape(*, run_id: str, row_id: str, token_id: str, node_id: str):
    """Create a landscape with one run, source node, row, token, and transform node.

    Returns the RecorderSetup from make_recorder_with_run.
    """
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
        plugin_name="FakeTransform",
    )
    row = setup.factory.data_flow.create_row(
        run_id=run_id,
        source_node_id="source-0",
        row_index=0,
        data={"amount": "not_an_int"},
        row_id=row_id,
    )
    setup.factory.data_flow.create_token(row_id=row.row_id, token_id=token_id)
    return setup


class TestDeclarationContractViolationRoundTrip:
    """Verify DeclarationContractViolation serializes losslessly through the Landscape."""

    def test_violation_payload_survives_landscape_round_trip(self) -> None:
        """to_audit_dict() must be fully recoverable via explain().

        Flow:
          1. Build a DeclarationContractViolation with nested payload.
          2. Record it to the Landscape as a FAILED node state via
             ExecutionRepository (the same code path NodeStateGuard uses).
          3. Call explain() on the token.
          4. Parse the NodeStateFailed.error_json and assert every payload
             field is present and correct — including nested structures.
        """
        run_id = "run-roundtrip"
        row_id = "row-roundtrip"
        token_id = "tok-roundtrip"
        node_id = "n-roundtrip"

        setup = _setup_landscape(
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            node_id=node_id,
        )

        violation = DeclarationContractViolation(
            contract_name="test_roundtrip",
            plugin="FakeTransform",
            node_id=node_id,
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            payload={
                "field_name": "amount",
                "expected_type": "int",
                "observed_type": "str",
                "nested": {"inner": [1, 2, 3]},
            },
            message="round-trip test violation",
        )

        audit_context = violation.to_audit_dict()

        exc_error = ExecutionError(
            exception=str(violation),
            exception_type=type(violation).__name__,
            phase="executor_post_process",
            context=audit_context,
        )

        state = setup.factory.execution.begin_node_state(
            token_id=token_id,
            node_id=node_id,
            run_id=run_id,
            step_index=1,
            input_data={"amount": "not_an_int"},
        )

        setup.factory.execution.complete_node_state(
            state.state_id,
            NodeStateStatus.FAILED,
            duration_ms=1.0,
            error=exc_error,
        )

        lineage = explain(
            query=setup.factory.query,
            data_flow=setup.factory.data_flow,
            run_id=run_id,
            token_id=token_id,
        )

        assert lineage is not None, "explain() returned None — token not found"

        failed_states = [ns for ns in lineage.node_states if isinstance(ns, NodeStateFailed)]
        assert len(failed_states) == 1, f"expected 1 FAILED node state, got {len(failed_states)}"

        failed = failed_states[0]
        assert failed.error_json is not None, "FAILED node state has no error_json"

        error_record = json.loads(failed.error_json)
        # error_json structure: {"exception": ..., "type": ..., "context": {...}}
        context = error_record["context"]

        assert context["exception_type"] == "DeclarationContractViolation"
        assert context["contract_name"] == "test_roundtrip"
        assert context["plugin"] == "FakeTransform"
        assert context["node_id"] == node_id
        assert context["run_id"] == run_id
        assert context["row_id"] == row_id
        assert context["token_id"] == token_id
        assert context["message"] == "round-trip test violation"

        payload = context["payload"]
        assert payload["field_name"] == "amount"
        assert payload["expected_type"] == "int"
        assert payload["observed_type"] == "str"
        assert payload["nested"]["inner"] == [1, 2, 3]

    def test_secrets_in_payload_are_scrubbed_before_landscape_write(self) -> None:
        """Reviewer B7/F-4: audit record must never contain unredacted secrets.

        The scrub happens in to_audit_dict() before the context reaches the
        Landscape. Verify the redacted form is what survives the round-trip.
        """
        run_id = "run-secret"
        row_id = "row-secret"
        token_id = "tok-secret"
        node_id = "n-secret"

        setup = _setup_landscape(
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            node_id=node_id,
        )

        violation = DeclarationContractViolation(
            contract_name="secret_test",
            plugin="FakeTransform",
            node_id=node_id,
            run_id=run_id,
            row_id=row_id,
            token_id=token_id,
            payload={"api_key": "sk-abcdef1234567890abcdef1234567890"},
            message="secret test",
        )

        audit_context = violation.to_audit_dict()

        exc_error = ExecutionError(
            exception=str(violation),
            exception_type=type(violation).__name__,
            phase="executor_post_process",
            context=audit_context,
        )

        state = setup.factory.execution.begin_node_state(
            token_id=token_id,
            node_id=node_id,
            run_id=run_id,
            step_index=1,
            input_data={"api_key": "[redacted-in-input]"},
        )

        setup.factory.execution.complete_node_state(
            state.state_id,
            NodeStateStatus.FAILED,
            duration_ms=1.0,
            error=exc_error,
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

        error_record = json.loads(failed_states[0].error_json)
        context = error_record["context"]

        # The raw secret must not appear anywhere in the serialized audit record.
        assert "sk-abcdef" not in json.dumps(context)
        assert context["payload"]["api_key"] == "<redacted-secret>"
