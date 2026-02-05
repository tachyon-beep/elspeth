"""Tests for contract propagation in batch transforms' single-row fallback path.

P2-2026-02-05: Batch LLM transforms have a _process_single method that processes
single rows by wrapping them in a list and calling _process_batch. When converting
the multi-row result back to single-row, the contract must be preserved so downstream
transforms can access LLM-added fields.
"""

from unittest.mock import Mock, patch

import pytest

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.plugins.context import PluginContext
from elspeth.plugins.llm.azure_batch import AzureBatchLLMTransform
from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchLLMTransform
from elspeth.plugins.results import TransformResult


class TestAzureBatchSingleRowContractPropagation:
    """Test contract propagation through AzureBatchLLMTransform._process_single."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Plugin context with required methods."""
        ctx = Mock(spec=PluginContext)
        ctx.run_id = "test_run"
        ctx.state_id = "state_1"
        ctx.record_call = Mock()
        ctx.get_checkpoint = Mock(return_value=None)
        ctx.update_checkpoint = Mock()
        ctx.clear_checkpoint = Mock()
        return ctx

    @pytest.fixture
    def input_contract(self) -> SchemaContract:
        """Input contract with customer_id field."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("customer_id", "customer_id", str, True, "declared"),),
            locked=True,
        )

    @pytest.fixture
    def output_contract(self) -> SchemaContract:
        """Output contract with customer_id + llm_response fields."""
        return SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract("customer_id", "customer_id", str, True, "declared"),
                FieldContract("llm_response", "llm_response", str, True, "inferred"),
            ),
            locked=True,
        )

    def test_process_single_preserves_contract_from_batch_result(
        self,
        ctx: PluginContext,
        input_contract: SchemaContract,
        output_contract: SchemaContract,
    ) -> None:
        """_process_single preserves contract from _process_batch result.

        When _process_single wraps a single row and calls _process_batch,
        the batch result includes an OBSERVED contract with all output fields.
        This contract must be propagated to the single-row result so downstream
        transforms can access LLM-added fields like 'llm_response'.
        """
        config = {
            "deployment_name": "test-deployment",
            "api_version": "2024-10-01",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "system_prompt": "You are a classifier",
            "template": "Classify: {{text}}",
            "response_field": "llm_response",
            "max_tokens": 100,
            "temperature": 0.0,
            "schema": {"mode": "observed"},
        }
        transform = AzureBatchLLMTransform(config)

        # Input row
        input_row = PipelineRow({"customer_id": "C001", "text": "hello"}, input_contract)

        # Mock _process_batch to return success_multi with contract
        # This simulates what _download_results does when batch completes
        batch_output_row = {"customer_id": "C001", "text": "hello", "llm_response": "classified"}
        batch_result = TransformResult.success_multi(
            [batch_output_row],
            success_reason={"action": "enriched", "fields_added": ["llm_response"]},
            contract=output_contract,
        )

        with patch.object(transform, "_process_batch", return_value=batch_result):
            result = transform._process_single(input_row, ctx)

        # Verify result structure
        assert result.status == "success"
        assert result.row is not None
        assert result.rows is None  # Single-row result

        # CRITICAL: Contract must be preserved
        assert result.contract is not None, "Contract lost in _process_single!"
        assert result.contract == output_contract

        # Verify downstream transforms can access LLM-added fields
        # If contract is missing, TransformExecutor would fall back to output_schema
        # which doesn't include llm_response, causing KeyError downstream
        try:
            resolved = result.contract.resolve_name("llm_response")
            assert resolved == "llm_response", f"Expected 'llm_response', got '{resolved}'"
        except KeyError:
            pytest.fail("Contract missing 'llm_response' field - downstream access would fail!")


class TestOpenRouterBatchSingleRowContractPropagation:
    """Test contract propagation through OpenRouterBatchLLMTransform._process_single."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Plugin context with required methods."""
        ctx = Mock(spec=PluginContext)
        ctx.run_id = "test_run"
        ctx.state_id = "state_1"
        ctx.record_call = Mock()
        ctx.get_checkpoint = Mock(return_value=None)
        ctx.update_checkpoint = Mock()
        ctx.clear_checkpoint = Mock()
        return ctx

    @pytest.fixture
    def input_contract(self) -> SchemaContract:
        """Input contract with customer_id field."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("customer_id", "customer_id", str, True, "declared"),),
            locked=True,
        )

    @pytest.fixture
    def output_contract(self) -> SchemaContract:
        """Output contract with customer_id + llm_response fields."""
        return SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract("customer_id", "customer_id", str, True, "declared"),
                FieldContract("llm_response", "llm_response", str, True, "inferred"),
            ),
            locked=True,
        )

    def test_process_single_preserves_contract_from_batch_result(
        self,
        ctx: PluginContext,
        input_contract: SchemaContract,
        output_contract: SchemaContract,
    ) -> None:
        """_process_single preserves contract from _process_batch result.

        Same test as AzureBatch but for OpenRouterBatch. Both transforms share
        the same pattern and had the same bug.
        """
        config = {
            "model": "anthropic/claude-3.5-sonnet",
            "api_key": "test-key",
            "system_prompt": "You are a classifier",
            "template": "Classify: {{text}}",
            "response_field": "llm_response",
            "max_tokens": 100,
            "temperature": 0.0,
            "schema": {"mode": "observed"},
        }
        transform = OpenRouterBatchLLMTransform(config)

        # Input row
        input_row = PipelineRow({"customer_id": "C001", "text": "hello"}, input_contract)

        # Mock _process_batch to return success_multi with contract
        batch_output_row = {"customer_id": "C001", "text": "hello", "llm_response": "classified"}
        batch_result = TransformResult.success_multi(
            [batch_output_row],
            success_reason={"action": "enriched", "fields_added": ["llm_response"]},
            contract=output_contract,
        )

        with patch.object(transform, "_process_batch", return_value=batch_result):
            result = transform._process_single(input_row, ctx)

        # Verify result structure
        assert result.status == "success"
        assert result.row is not None
        assert result.rows is None  # Single-row result

        # CRITICAL: Contract must be preserved
        assert result.contract is not None, "Contract lost in _process_single!"
        assert result.contract == output_contract

        # Verify downstream transforms can access LLM-added fields
        try:
            resolved = result.contract.resolve_name("llm_response")
            assert resolved == "llm_response", f"Expected 'llm_response', got '{resolved}'"
        except KeyError:
            pytest.fail("Contract missing 'llm_response' field - downstream access would fail!")
