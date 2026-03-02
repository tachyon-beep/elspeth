# tests/unit/contracts/transform_contracts/test_azure_multi_query_contract.py
"""Contract tests for multi-query LLM transform (Azure provider).

Note: Row-based contract tests (TransformContractPropertyTestBase) were removed because
LLMTransform uses BatchTransformMixin and doesn't support process(). The
attribute tests (name, schema, determinism) are now included in BatchTransformContractTestBase.

Migrated from AzureMultiQueryLLMTransform to unified LLMTransform with provider="azure"
and queries dict format (T10 Phase B consolidation).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest

from elspeth.contracts.plugin_context import PluginContext
from elspeth.plugins.infrastructure.batching.mixin import BatchTransformMixin
from elspeth.plugins.transforms.llm.transform import LLMTransform

from .test_batch_transform_protocol import BatchTransformContractTestBase


def _make_mock_response(content: str = '{"score": 85, "rationale": "test"}') -> Mock:
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content=content))]
    mock_response.model = "gpt-4o"
    mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5)
    mock_response.model_dump = Mock(return_value={})
    return mock_response


def _make_mock_context() -> Mock:
    ctx = Mock(spec=PluginContext)
    ctx.run_id = "test-run-001"
    ctx.state_id = "state-001"
    ctx.landscape = Mock()
    ctx.landscape.record_call = Mock()
    ctx.landscape.allocate_call_index = Mock(return_value=0)
    return ctx


@pytest.fixture(autouse=True)
def mock_azure_openai():
    with patch("openai.AzureOpenAI") as mock_azure_class:
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _make_mock_response()
        mock_azure_class.return_value = mock_client
        yield mock_client


class TestMultiQueryLLMSpecific:
    def test_query_expansion_produces_expected_output_fields(self) -> None:
        """6 configured queries produce 6 sets of prefixed output fields."""
        transform = LLMTransform(
            {
                "provider": "azure",
                "deployment_name": "gpt-4o",
                "endpoint": "https://test.openai.azure.com",
                "api_key": "test-key",
                "template": "{{ row.text_content }}",
                "schema": {"mode": "observed"},
                "required_input_fields": [],
                "queries": {
                    "cs1_crit1": {
                        "input_fields": {"text_content": "a"},
                        "output_fields": [{"suffix": "score", "type": "integer"}],
                    },
                    "cs1_crit2": {
                        "input_fields": {"text_content": "a"},
                        "output_fields": [{"suffix": "rating", "type": "integer"}],
                    },
                    "cs1_crit3": {
                        "input_fields": {"text_content": "a"},
                        "output_fields": [{"suffix": "grade", "type": "integer"}],
                    },
                    "cs2_crit1": {
                        "input_fields": {"text_content": "b"},
                        "output_fields": [{"suffix": "eval_score", "type": "integer"}],
                    },
                    "cs2_crit2": {
                        "input_fields": {"text_content": "b"},
                        "output_fields": [{"suffix": "eval_rating", "type": "integer"}],
                    },
                    "cs2_crit3": {
                        "input_fields": {"text_content": "b"},
                        "output_fields": [{"suffix": "eval_grade", "type": "integer"}],
                    },
                },
            }
        )
        transform.on_error = "quarantine_sink"

        # Observable: declared_output_fields contains prefixed fields for each query
        declared = transform.declared_output_fields
        expected_fields = {
            "cs1_crit1_score",
            "cs1_crit2_rating",
            "cs1_crit3_grade",
            "cs2_crit1_eval_score",
            "cs2_crit2_eval_rating",
            "cs2_crit3_eval_grade",
        }
        assert expected_fields.issubset(declared), f"Missing expected output fields: {expected_fields - declared}"

    def test_creates_tokens_false(self) -> None:
        transform = LLMTransform(
            {
                "provider": "azure",
                "deployment_name": "gpt-4o",
                "endpoint": "https://test.openai.azure.com",
                "api_key": "test-key",
                "template": "{{ row.text_content }}",
                "schema": {"mode": "observed"},
                "required_input_fields": [],
                "queries": {
                    "cs1_crit1": {
                        "input_fields": {"text_content": "a"},
                        "output_fields": [{"suffix": "score", "type": "integer"}],
                    },
                },
            }
        )
        transform.on_error = "quarantine_sink"

        assert transform.creates_tokens is False


class TestMultiQueryBatchContract(BatchTransformContractTestBase):
    """Verify multi-query LLM transform honors BatchTransformMixin contract."""

    @pytest.fixture
    def batch_transform(self) -> BatchTransformMixin:
        """Provide unconfigured transform (no connect_output yet)."""
        t = LLMTransform(
            {
                "provider": "azure",
                "deployment_name": "gpt-4o",
                "endpoint": "https://test.openai.azure.com",
                "api_key": "test-key",
                "template": "{{ row.text_content }} {{ row.criterion_name }}",
                "schema": {"mode": "observed"},
                "required_input_fields": [],
                "queries": {
                    "cs1_test_criterion": {
                        "input_fields": {"text_content": "cs1_a", "criterion_name": "cs1_b"},
                        "output_fields": [
                            {"suffix": "score", "type": "integer"},
                            {"suffix": "rationale", "type": "string"},
                        ],
                    },
                },
            }
        )
        t.on_error = "quarantine_sink"
        return t

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        return {"cs1_a": "value_a", "cs1_b": "value_b"}
