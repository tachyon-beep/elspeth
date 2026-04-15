"""Tests for PluginAuditWriter protocol and adapter delegation routing."""

from __future__ import annotations

from unittest.mock import MagicMock, sentinel

import pytest

from elspeth.contracts import CallStatus, CallType
from elspeth.core.landscape.data_flow_repository import DataFlowRepository
from elspeth.core.landscape.execution_repository import ExecutionRepository
from elspeth.core.landscape.factory import _PluginAuditWriterAdapter
from elspeth.core.landscape.run_lifecycle_repository import RunLifecycleRepository


@pytest.fixture()
def repos() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Create mock repositories with spec matching the real classes."""
    execution = MagicMock(spec=ExecutionRepository)
    data_flow = MagicMock(spec=DataFlowRepository)
    run_lifecycle = MagicMock(spec=RunLifecycleRepository)
    return execution, data_flow, run_lifecycle


@pytest.fixture()
def writer(
    repos: tuple[MagicMock, MagicMock, MagicMock],
) -> _PluginAuditWriterAdapter:
    execution, data_flow, run_lifecycle = repos
    return _PluginAuditWriterAdapter(execution, data_flow, run_lifecycle)


class TestAdapterConstruction:
    """Verify the adapter constructs without error and has the right type."""

    def test_adapter_constructs_successfully(self, writer: _PluginAuditWriterAdapter) -> None:
        assert isinstance(writer, _PluginAuditWriterAdapter)


class TestCallRecordingRoutesToExecution:
    """Verify call-related methods delegate to ExecutionRepository."""

    def test_allocate_call_index_routes_to_execution(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        execution, _data_flow, _run_lifecycle = repos
        execution.allocate_call_index.return_value = 42

        result = writer.allocate_call_index("state-1")

        assert result == 42
        execution.allocate_call_index.assert_called_once_with("state-1")
        # DataFlowRepository does not have allocate_call_index — if it
        # routed there, the adapter would have crashed.

    def test_record_call_routes_to_execution(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        execution, _data_flow, _run_lifecycle = repos
        execution.record_call.return_value = sentinel.call

        payload = MagicMock()  # CallPayload is a Protocol; use a mock
        result = writer.record_call("state-1", 0, CallType.HTTP, CallStatus.SUCCESS, payload)

        assert result is sentinel.call
        execution.record_call.assert_called_once()
        # Verify the first positional arg routed correctly
        assert execution.record_call.call_args[0][0] == "state-1"


class TestErrorRecordingRoutesToDataFlow:
    """Verify error recording methods delegate to DataFlowRepository."""

    def test_record_validation_error_routes_to_data_flow(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        _execution, data_flow, _run_lifecycle = repos
        data_flow.record_validation_error.return_value = "err-1"

        result = writer.record_validation_error("run-1", "node-1", {"field": "value"}, "bad data", "strict", "sink-1")

        assert result == "err-1"
        data_flow.record_validation_error.assert_called_once()
        # Verify run_id routed to data_flow
        assert data_flow.record_validation_error.call_args[0][0] == "run-1"


class TestNodeStateRoutesToExecution:
    """Verify get_node_state delegates to ExecutionRepository."""

    def test_get_node_state_routes_to_execution(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        execution, _data_flow, _run_lifecycle = repos
        execution.get_node_state.return_value = sentinel.state

        result = writer.get_node_state("state-1")

        assert result is sentinel.state
        execution.get_node_state.assert_called_once_with("state-1")


class TestOperationCallRoutesToExecution:
    """Verify record_operation_call delegates to ExecutionRepository."""

    def test_record_operation_call_routes_to_execution(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        execution, _data_flow, _run_lifecycle = repos
        execution.record_operation_call.return_value = sentinel.call

        payload = MagicMock()
        result = writer.record_operation_call("op-1", CallType.HTTP, CallStatus.SUCCESS, payload)

        assert result is sentinel.call
        execution.record_operation_call.assert_called_once()
        assert execution.record_operation_call.call_args[0][0] == "op-1"


class TestRoutingEventRoutesToExecution:
    """Verify routing event methods delegate to ExecutionRepository."""

    def test_record_routing_event_routes_to_execution(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        from elspeth.contracts import RoutingMode

        execution, _data_flow, _run_lifecycle = repos
        execution.record_routing_event.return_value = sentinel.event

        result = writer.record_routing_event("state-1", "edge-1", RoutingMode.MOVE)

        assert result is sentinel.event
        execution.record_routing_event.assert_called_once()
        assert execution.record_routing_event.call_args[0][0] == "state-1"

    def test_record_routing_events_routes_to_execution(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        execution, _data_flow, _run_lifecycle = repos
        execution.record_routing_events.return_value = [sentinel.event]

        result = writer.record_routing_events("state-1", [])

        assert result == [sentinel.event]
        execution.record_routing_events.assert_called_once()


class TestTransformErrorRoutesToDataFlow:
    """Verify record_transform_error delegates to DataFlowRepository."""

    def test_record_transform_error_routes_to_data_flow(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        from elspeth.contracts.audit import TokenRef
        from elspeth.contracts.errors import TransformErrorReason

        _execution, data_flow, _run_lifecycle = repos
        data_flow.record_transform_error.return_value = "err-1"

        ref = TokenRef(token_id="tok-1", run_id="run-1")
        reason = TransformErrorReason(reason="api_error", error_type="ValueError", message="bad")
        result = writer.record_transform_error(ref, "xform-1", {"field": "val"}, reason, "sink-1")

        assert result == "err-1"
        data_flow.record_transform_error.assert_called_once()


class TestContractMethodsRouteToDataFlow:
    """Verify contract-related methods delegate to DataFlowRepository."""

    def test_update_node_output_contract_routes_to_data_flow(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        _execution, data_flow, _run_lifecycle = repos

        mock_contract = MagicMock()
        writer.update_node_output_contract("run-1", "node-1", mock_contract)

        data_flow.update_node_output_contract.assert_called_once_with("run-1", "node-1", mock_contract)

    def test_get_node_contracts_routes_to_data_flow(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        _execution, data_flow, _run_lifecycle = repos
        data_flow.get_node_contracts.return_value = (sentinel.input, sentinel.output)

        result = writer.get_node_contracts("run-1", "node-1")

        assert result == (sentinel.input, sentinel.output)
        data_flow.get_node_contracts.assert_called_once()


class TestReadinessCheckRoutesToRunLifecycle:
    """Verify record_readiness_check delegates to RunLifecycleRepository."""

    def test_record_readiness_check_routes_to_run_lifecycle(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        _execution, _data_flow, run_lifecycle = repos

        writer.record_readiness_check(
            "run-1",
            name="chroma",
            collection="docs",
            reachable=True,
            count=42,
            message="OK",
        )

        run_lifecycle.record_readiness_check.assert_called_once_with(
            "run-1",
            name="chroma",
            collection="docs",
            reachable=True,
            count=42,
            message="OK",
        )


class TestRunLifecycleRoutesToRunLifecycle:
    """Verify run lifecycle methods delegate to RunLifecycleRepository."""

    def test_get_source_field_resolution_routes_to_run_lifecycle(
        self,
        writer: _PluginAuditWriterAdapter,
        repos: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        _execution, _data_flow, run_lifecycle = repos
        run_lifecycle.get_source_field_resolution.return_value = {"a": "b"}

        result = writer.get_source_field_resolution("run-1")

        assert result == {"a": "b"}
        run_lifecycle.get_source_field_resolution.assert_called_once_with("run-1")
