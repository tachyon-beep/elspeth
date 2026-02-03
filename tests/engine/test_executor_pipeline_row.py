"""Tests for executor PipelineRow handling.

Tests that TransformExecutor:
1. Passes PipelineRow (not dict) to transform.process()
2. Extracts dict from PipelineRow for Landscape recording
3. Sets ctx.contract from token.row_data.contract
4. Creates new PipelineRow from result using correct contract
5. Crashes if no contract available (B6 fix)
"""

from contextlib import nullcontext
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from elspeth.contracts import TransformResult
from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract() -> SchemaContract:
    """Create a simple test contract."""
    return SchemaContract(
        mode="FLEXIBLE",
        fields=(
            FieldContract(
                normalized_name="value",
                original_name="'value'",
                python_type=str,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


def _make_output_contract() -> SchemaContract:
    """Create a contract for transform output (different from input)."""
    return SchemaContract(
        mode="FLEXIBLE",
        fields=(
            FieldContract(
                normalized_name="value",
                original_name="'value'",
                python_type=str,
                required=True,
                source="declared",
            ),
            FieldContract(
                normalized_name="processed",
                original_name="'processed'",
                python_type=bool,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


class TestTransformExecutorPipelineRow:
    """Tests for TransformExecutor with PipelineRow."""

    def test_execute_transform_passes_pipeline_row_to_plugin(self) -> None:
        """TransformExecutor should pass PipelineRow to transform.process()."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - configure spec to avoid MagicMock auto-creating 'accept' attr
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.success(
            {"value": "processed"},
            success_reason={"action": "test"},
            contract=contract,
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        _result, _updated_token, _error_sink = executor.execute_transform(
            transform=mock_transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify PipelineRow was passed to transform.process()
        mock_transform.process.assert_called_once()
        call_args = mock_transform.process.call_args
        passed_row = call_args[0][0]
        assert isinstance(passed_row, PipelineRow), f"Expected PipelineRow, got {type(passed_row)}"
        assert passed_row["value"] == "test"

    def test_execute_transform_extracts_dict_for_landscape(self) -> None:
        """TransformExecutor should extract dict for Landscape recording."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - configure spec to avoid MagicMock auto-creating 'accept' attr
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.success(
            {"value": "processed"},
            success_reason={"action": "test"},
            contract=contract,
        )

        # Mock recorder - capture what gets passed
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.execute_transform(
            transform=mock_transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify dict was passed to begin_node_state (for Landscape recording)
        mock_recorder.begin_node_state.assert_called_once()
        call_kwargs = mock_recorder.begin_node_state.call_args[1]
        input_data = call_kwargs["input_data"]
        assert isinstance(input_data, dict), f"Expected dict for Landscape, got {type(input_data)}"
        assert input_data == {"value": "test"}

    def test_execute_transform_sets_ctx_contract(self) -> None:
        """TransformExecutor should set ctx.contract from token.row_data.contract."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - capture the context passed to process()
        captured_ctx = None

        def capture_ctx(row_data, ctx):
            nonlocal captured_ctx
            captured_ctx = ctx
            return TransformResult.success(
                {"value": "processed"},
                success_reason={"action": "test"},
                contract=contract,
            )

        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process = capture_ctx

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context - initially no contract
        ctx = PluginContext(run_id="run_001", config={})
        assert ctx.contract is None

        # Execute
        executor.execute_transform(
            transform=mock_transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify ctx.contract was set from token.row_data.contract
        assert captured_ctx is not None
        assert captured_ctx.contract is contract

    def test_execute_transform_creates_pipeline_row_from_result(self) -> None:
        """TransformExecutor should create PipelineRow from result dict + contract."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        input_contract = _make_contract()
        output_contract = _make_output_contract()
        row = PipelineRow({"value": "test"}, input_contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - returns different contract on output
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.success(
            {"value": "processed", "processed": True},
            success_reason={"action": "test"},
            contract=output_contract,  # Transform provides output contract
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        _result, updated_token, _error_sink = executor.execute_transform(
            transform=mock_transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify updated token has PipelineRow with output contract
        assert isinstance(updated_token.row_data, PipelineRow)
        assert updated_token.row_data["value"] == "processed"
        assert updated_token.row_data["processed"] is True
        assert updated_token.row_data.contract is output_contract

    def test_execute_transform_uses_input_contract_as_fallback(self) -> None:
        """When result has no contract, should use input token's contract."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - NO contract on result (typical passthrough transform)
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.success(
            {"value": "modified"},
            success_reason={"action": "passthrough"},
            contract=None,  # No output contract - should use input contract
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        _result, updated_token, _error_sink = executor.execute_transform(
            transform=mock_transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify updated token uses input contract as fallback
        assert isinstance(updated_token.row_data, PipelineRow)
        assert updated_token.row_data.contract is contract

    def test_execute_transform_error_preserves_token(self) -> None:
        """When transform returns error, token should be unchanged."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - returns error
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = "discard"  # Has error handler
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.error(
            reason={"reason": "test_failure"},
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        _result, updated_token, _error_sink = executor.execute_transform(
            transform=mock_transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify token is unchanged on error
        assert updated_token is token
        assert updated_token.row_data is row

    def test_execute_transform_hashes_dict_not_pipeline_row(self) -> None:
        """stable_hash should be called with dict, not PipelineRow."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - configure spec to avoid MagicMock auto-creating 'accept' attr
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.success(
            {"value": "processed"},
            success_reason={"action": "test"},
            contract=contract,
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Patch stable_hash to verify what gets passed
        with patch("elspeth.engine.executors.stable_hash") as mock_hash:
            mock_hash.return_value = "test_hash"

            executor.execute_transform(
                transform=mock_transform,
                token=token,
                ctx=ctx,
                step_in_pipeline=0,
            )

            # First call should be for input hash - should receive dict
            first_call_arg = mock_hash.call_args_list[0][0][0]
            assert isinstance(first_call_arg, dict), f"stable_hash should receive dict, got {type(first_call_arg)}"

    def test_execute_transform_crashes_if_no_contract_available(self) -> None:
        """Should crash if neither result nor input has contract (B6 fix)."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow - we'll mock the contract property to return None
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock transform - returns success with NO contract
        mock_transform = MagicMock()
        mock_transform.name = "test_transform"
        mock_transform.node_id = "transform_001"
        mock_transform._on_error = None
        # Delete accept to prevent batch transform detection
        del mock_transform.accept
        mock_transform.process.return_value = TransformResult.success(
            {"value": "processed"},
            success_reason={"action": "test"},
            contract=None,  # No output contract
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.transform_span.return_value = nullcontext()

        # Create executor
        executor = TransformExecutor(mock_recorder, mock_span_factory)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Mock the contract property on row_data to return None
        # This simulates the edge case where input token has no contract
        with patch.object(type(token.row_data), "contract", new_callable=PropertyMock) as mock_contract:
            mock_contract.return_value = None

            # Execute - should raise ValueError
            with pytest.raises(ValueError) as exc_info:
                executor.execute_transform(
                    transform=mock_transform,
                    token=token,
                    ctx=ctx,
                    step_in_pipeline=0,
                )

            # Verify error message is clear
            assert "Cannot create PipelineRow: no contract available" in str(exc_info.value)
            assert "test_transform" in str(exc_info.value)


class TestGateExecutorPipelineRow:
    """Tests for GateExecutor with PipelineRow."""

    def test_execute_gate_passes_pipeline_row_to_plugin(self) -> None:
        """GateExecutor should pass PipelineRow to gate.evaluate()."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate - capture what gets passed
        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate.return_value = GateResult(
            row={"value": "test"},
            action=RoutingAction.continue_(),
            contract=contract,
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory - use nullcontext for proper context manager behavior
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map for continue routing
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.execute_gate(
            gate=mock_gate,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify PipelineRow was passed to gate.evaluate()
        mock_gate.evaluate.assert_called_once()
        call_args = mock_gate.evaluate.call_args
        passed_row = call_args[0][0]
        assert isinstance(passed_row, PipelineRow), f"Expected PipelineRow, got {type(passed_row)}"
        assert passed_row["value"] == "test"

    def test_execute_gate_sets_ctx_contract(self) -> None:
        """GateExecutor should set ctx.contract from token.row_data.contract."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate - capture the context passed to evaluate()
        captured_ctx = None

        def capture_ctx(row_data, ctx):
            nonlocal captured_ctx
            captured_ctx = ctx
            return GateResult(
                row={"value": "test"},
                action=RoutingAction.continue_(),
                contract=contract,
            )

        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate = capture_ctx

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map for continue routing
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context - initially no contract
        ctx = PluginContext(run_id="run_001", config={})
        assert ctx.contract is None

        # Execute
        executor.execute_gate(
            gate=mock_gate,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify ctx.contract was set from token.row_data.contract
        assert captured_ctx is not None
        assert captured_ctx.contract is contract

    def test_execute_gate_extracts_dict_for_landscape(self) -> None:
        """GateExecutor should extract dict for Landscape recording."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate
        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate.return_value = GateResult(
            row={"value": "test"},
            action=RoutingAction.continue_(),
            contract=contract,
        )

        # Mock recorder - capture what gets passed
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map for continue routing
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.execute_gate(
            gate=mock_gate,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify dict was passed to begin_node_state (for Landscape recording)
        mock_recorder.begin_node_state.assert_called_once()
        call_kwargs = mock_recorder.begin_node_state.call_args[1]
        input_data = call_kwargs["input_data"]
        assert isinstance(input_data, dict), f"Expected dict for Landscape, got {type(input_data)}"
        assert input_data == {"value": "test"}

    def test_execute_gate_creates_pipeline_row_from_result(self) -> None:
        """GateExecutor should create PipelineRow from result using correct contract."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        input_contract = _make_contract()
        output_contract = _make_output_contract()
        row = PipelineRow({"value": "test"}, input_contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate - returns row with modified data and new contract
        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate.return_value = GateResult(
            row={"value": "modified", "processed": True},
            action=RoutingAction.continue_(),
            contract=output_contract,  # Gate provides output contract
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map for continue routing
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        outcome = executor.execute_gate(
            gate=mock_gate,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify updated token has PipelineRow with output contract
        assert isinstance(outcome.updated_token.row_data, PipelineRow)
        assert outcome.updated_token.row_data["value"] == "modified"
        assert outcome.updated_token.row_data["processed"] is True
        assert outcome.updated_token.row_data.contract is output_contract

    def test_execute_gate_uses_input_contract_as_fallback(self) -> None:
        """When GateResult has no contract, should use input token's contract."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate - NO contract on result (typical passthrough gate)
        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate.return_value = GateResult(
            row={"value": "modified"},
            action=RoutingAction.continue_(),
            contract=None,  # No output contract - should use input contract
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map for continue routing
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        outcome = executor.execute_gate(
            gate=mock_gate,
            token=token,
            ctx=ctx,
            step_in_pipeline=0,
        )

        # Verify updated token uses input contract as fallback
        assert isinstance(outcome.updated_token.row_data, PipelineRow)
        assert outcome.updated_token.row_data.contract is contract

    def test_execute_gate_hashes_dict_not_pipeline_row(self) -> None:
        """stable_hash should be called with dict, not PipelineRow."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate
        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate.return_value = GateResult(
            row={"value": "test"},
            action=RoutingAction.continue_(),
            contract=contract,
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Patch stable_hash to verify what gets passed
        with patch("elspeth.engine.executors.stable_hash") as mock_hash:
            mock_hash.return_value = "test_hash"

            executor.execute_gate(
                gate=mock_gate,
                token=token,
                ctx=ctx,
                step_in_pipeline=0,
            )

            # First call should be for input hash - should receive dict
            first_call_arg = mock_hash.call_args_list[0][0][0]
            assert isinstance(first_call_arg, dict), f"stable_hash should receive dict, got {type(first_call_arg)}"

    def test_execute_gate_crashes_if_no_contract_available(self) -> None:
        """Should crash if neither result nor input has contract (B6 fix)."""
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow - we'll mock the contract property to return None
        contract = _make_contract()
        row = PipelineRow({"value": "test"}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=row)

        # Mock gate - returns success with NO contract
        mock_gate = MagicMock()
        mock_gate.name = "test_gate"
        mock_gate.node_id = "gate_001"
        mock_gate.evaluate.return_value = GateResult(
            row={"value": "processed"},
            action=RoutingAction.continue_(),
            contract=None,  # No output contract
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.gate_span.return_value = nullcontext()

        # Create executor with edge_map
        edge_map = {("gate_001", "continue"): "edge_001"}
        executor = GateExecutor(mock_recorder, mock_span_factory, edge_map=edge_map)

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Mock the contract property on row_data to return None
        # This simulates the edge case where input token has no contract
        with patch.object(type(token.row_data), "contract", new_callable=PropertyMock) as mock_contract:
            mock_contract.return_value = None

            # Execute - should raise ValueError
            with pytest.raises(ValueError) as exc_info:
                executor.execute_gate(
                    gate=mock_gate,
                    token=token,
                    ctx=ctx,
                    step_in_pipeline=0,
                )

            # Verify error message is clear
            assert "Cannot create PipelineRow: no contract available" in str(exc_info.value)
            assert "test_gate" in str(exc_info.value)


class TestSinkExecutorPipelineRow:
    """Tests for SinkExecutor with PipelineRow.

    Sinks receive list[dict], NOT list[PipelineRow]. The SinkExecutor must
    extract dicts from PipelineRow before calling sink.write().

    Contract metadata is preserved in Landscape audit trail, not sink output.
    """

    def test_execute_sink_extracts_dicts_from_pipeline_rows(self) -> None:
        """SinkExecutor should extract dicts before calling sink.write()."""
        from elspeth.contracts import ArtifactDescriptor, PendingOutcome, RowOutcome
        from elspeth.engine.executors import SinkExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup tokens with PipelineRow
        contract = _make_contract()
        tokens = [
            TokenInfo(row_id="r1", token_id="t1", row_data=PipelineRow({"value": "a"}, contract)),
            TokenInfo(row_id="r2", token_id="t2", row_data=PipelineRow({"value": "b"}, contract)),
        ]

        # Mock sink - capture what gets passed to write()
        mock_sink = MagicMock()
        mock_sink.name = "test_sink"
        mock_sink.node_id = "sink_001"
        mock_sink.write.return_value = ArtifactDescriptor(
            artifact_type="csv",
            path_or_uri="/output/test.csv",
            content_hash="abc123",
            size_bytes=100,
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state
        mock_artifact = MagicMock()
        mock_recorder.register_artifact.return_value = mock_artifact

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.sink_span.return_value = nullcontext()

        # Create executor
        executor = SinkExecutor(mock_recorder, mock_span_factory, run_id="run_001")

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.write(
            sink=mock_sink,
            tokens=tokens,
            ctx=ctx,
            step_in_pipeline=5,
            sink_name="test_sink",
            pending_outcome=PendingOutcome(outcome=RowOutcome.COMPLETED),
        )

        # Verify dicts (not PipelineRow) were passed to sink.write()
        mock_sink.write.assert_called_once()
        call_args = mock_sink.write.call_args
        rows = call_args[0][0]
        assert len(rows) == 2
        assert all(isinstance(r, dict) for r in rows), f"Expected dicts, got {[type(r) for r in rows]}"
        assert all(not isinstance(r, PipelineRow) for r in rows), "Sink should not receive PipelineRow objects"
        assert rows == [{"value": "a"}, {"value": "b"}]

    def test_execute_sink_extracts_dict_for_landscape_input(self) -> None:
        """SinkExecutor should extract dict for Landscape input_data recording."""
        from elspeth.contracts import ArtifactDescriptor, PendingOutcome, RowOutcome
        from elspeth.engine.executors import SinkExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        token = TokenInfo(row_id="r1", token_id="t1", row_data=PipelineRow({"value": "test"}, contract))

        # Mock sink
        mock_sink = MagicMock()
        mock_sink.name = "test_sink"
        mock_sink.node_id = "sink_001"
        mock_sink.write.return_value = ArtifactDescriptor(
            artifact_type="csv",
            path_or_uri="/output/test.csv",
            content_hash="abc123",
            size_bytes=100,
        )

        # Mock recorder - capture what gets passed
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state
        mock_artifact = MagicMock()
        mock_recorder.register_artifact.return_value = mock_artifact

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.sink_span.return_value = nullcontext()

        # Create executor
        executor = SinkExecutor(mock_recorder, mock_span_factory, run_id="run_001")

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.write(
            sink=mock_sink,
            tokens=[token],
            ctx=ctx,
            step_in_pipeline=5,
            sink_name="test_sink",
            pending_outcome=PendingOutcome(outcome=RowOutcome.COMPLETED),
        )

        # Verify dict was passed to begin_node_state (for Landscape recording)
        mock_recorder.begin_node_state.assert_called_once()
        call_kwargs = mock_recorder.begin_node_state.call_args[1]
        input_data = call_kwargs["input_data"]
        assert isinstance(input_data, dict), f"Expected dict for Landscape input_data, got {type(input_data)}"
        assert not isinstance(input_data, PipelineRow), "Landscape should not receive PipelineRow objects"
        assert input_data == {"value": "test"}

    def test_execute_sink_extracts_dict_for_landscape_output(self) -> None:
        """SinkExecutor should extract dict for Landscape output_data recording."""
        from elspeth.contracts import ArtifactDescriptor, PendingOutcome, RowOutcome
        from elspeth.engine.executors import SinkExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow
        contract = _make_contract()
        token = TokenInfo(row_id="r1", token_id="t1", row_data=PipelineRow({"value": "test"}, contract))

        # Mock sink
        mock_sink = MagicMock()
        mock_sink.name = "test_sink"
        mock_sink.node_id = "sink_001"
        mock_sink.write.return_value = ArtifactDescriptor(
            artifact_type="csv",
            path_or_uri="/output/test.csv",
            content_hash="abc123",
            size_bytes=100,
        )

        # Mock recorder - capture what gets passed to complete_node_state
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state
        mock_artifact = MagicMock()
        mock_recorder.register_artifact.return_value = mock_artifact

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.sink_span.return_value = nullcontext()

        # Create executor
        executor = SinkExecutor(mock_recorder, mock_span_factory, run_id="run_001")

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.write(
            sink=mock_sink,
            tokens=[token],
            ctx=ctx,
            step_in_pipeline=5,
            sink_name="test_sink",
            pending_outcome=PendingOutcome(outcome=RowOutcome.COMPLETED),
        )

        # Verify dict was passed to complete_node_state output_data
        # complete_node_state is called once for successful sink write
        complete_calls = [c for c in mock_recorder.complete_node_state.call_args_list if c[1].get("output_data") is not None]
        assert len(complete_calls) == 1
        output_data = complete_calls[0][1]["output_data"]
        row_in_output = output_data["row"]
        assert isinstance(row_in_output, dict), f"Expected dict in output_data['row'], got {type(row_in_output)}"
        assert not isinstance(row_in_output, PipelineRow), "Landscape output should not contain PipelineRow"
        assert row_in_output == {"value": "test"}

    def test_execute_sink_preserves_all_fields_in_dict(self) -> None:
        """Sink should receive all fields, including extras not in contract."""
        from elspeth.contracts import ArtifactDescriptor, PendingOutcome, RowOutcome
        from elspeth.engine.executors import SinkExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        # Setup token with PipelineRow that has extra fields not in contract
        contract = _make_contract()  # Only declares 'value' field
        # PipelineRow allows extra fields in FLEXIBLE mode
        row_data = {"value": "test", "extra_field": "extra_value", "another": 123}
        token = TokenInfo(row_id="r1", token_id="t1", row_data=PipelineRow(row_data, contract))

        # Mock sink - capture what gets passed
        mock_sink = MagicMock()
        mock_sink.name = "test_sink"
        mock_sink.node_id = "sink_001"
        mock_sink.write.return_value = ArtifactDescriptor(
            artifact_type="csv",
            path_or_uri="/output/test.csv",
            content_hash="abc123",
            size_bytes=100,
        )

        # Mock recorder
        mock_recorder = MagicMock()
        mock_state = MagicMock()
        mock_state.state_id = "state_001"
        mock_recorder.begin_node_state.return_value = mock_state
        mock_artifact = MagicMock()
        mock_recorder.register_artifact.return_value = mock_artifact

        # Mock span factory
        mock_span_factory = MagicMock(spec=SpanFactory)
        mock_span_factory.sink_span.return_value = nullcontext()

        # Create executor
        executor = SinkExecutor(mock_recorder, mock_span_factory, run_id="run_001")

        # Create context
        ctx = PluginContext(run_id="run_001", config={})

        # Execute
        executor.write(
            sink=mock_sink,
            tokens=[token],
            ctx=ctx,
            step_in_pipeline=5,
            sink_name="test_sink",
            pending_outcome=PendingOutcome(outcome=RowOutcome.COMPLETED),
        )

        # Verify ALL fields are passed to sink, not just contract fields
        mock_sink.write.assert_called_once()
        call_args = mock_sink.write.call_args
        rows = call_args[0][0]
        assert len(rows) == 1
        assert rows[0] == {"value": "test", "extra_field": "extra_value", "another": 123}
