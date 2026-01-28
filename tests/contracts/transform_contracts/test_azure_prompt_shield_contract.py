# tests/contracts/transform_contracts/test_azure_prompt_shield_contract.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import pytest

from elspeth.plugins.batching.mixin import BatchTransformMixin
from elspeth.plugins.context import PluginContext
from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

from .test_batch_transform_protocol import BatchTransformContractTestBase
from .test_transform_protocol import TransformContractPropertyTestBase

if TYPE_CHECKING:
    from elspeth.plugins.protocols import TransformProtocol


def _make_clean_response() -> dict[str, Any]:
    return {
        "userPromptAnalysis": {"attackDetected": False},
        "documentsAnalysis": [{"attackDetected": False}],
    }


def _create_mock_http_response(response_data: dict[str, Any]) -> Mock:
    response = Mock()
    response.status_code = 200
    response.json.return_value = response_data
    response.raise_for_status = Mock()
    response.headers = {"content-type": "application/json"}
    response.content = b"{}"
    response.text = "{}"
    return response


def _make_mock_context() -> Mock:
    ctx = Mock(spec=PluginContext)
    ctx.run_id = "test-run-001"
    ctx.state_id = "state-001"
    ctx.landscape = Mock()
    ctx.landscape.record_call = Mock()
    return ctx


@pytest.fixture(autouse=True)
def mock_httpx_client():
    with patch("httpx.Client") as mock_client_class:
        yield mock_client_class


class TestAzurePromptShieldContract(TransformContractPropertyTestBase):
    @pytest.fixture
    def transform(self, mock_httpx_client: Mock) -> TransformProtocol:
        mock_response = _create_mock_http_response(_make_clean_response())
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = Mock(return_value=False)
        mock_httpx_client.return_value = mock_client_instance

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "on_error": "quarantine_sink",
            }
        )
        mock_ctx = _make_mock_context()
        transform.on_start(mock_ctx)
        return transform

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        return {"prompt": "What is the weather?", "id": 1}

    @pytest.fixture
    def ctx(self) -> Mock:
        return _make_mock_context()


# Note: Error contract tests removed - BatchTransformMixin transforms don't use process().
# Error handling is tested in tests/plugins/transforms/azure/test_prompt_shield.py via accept().


class TestAzurePromptShieldBatchContract(BatchTransformContractTestBase):
    """Verify Azure Prompt Shield transform honors BatchTransformMixin contract.

    These tests are critical for production use as they verify:
    - accept() returns immediately (non-blocking pipeline throughput)
    - Results arrive via OutputPort in FIFO order (audit trail integrity)
    - Token/state_id tracking is correct (lineage preservation)
    - Lifecycle methods are idempotent (crash recovery safety)
    """

    @pytest.fixture(autouse=True)
    def mock_httpx_for_batch(self):
        """Mock httpx.Client for all batch contract tests."""
        with patch("httpx.Client") as mock_client_class:
            mock_response = _create_mock_http_response(_make_clean_response())
            mock_client_instance = Mock()
            mock_client_instance.post.return_value = mock_response
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_class.return_value = mock_client_instance
            yield mock_client_class

    @pytest.fixture
    def batch_transform(self) -> BatchTransformMixin:
        """Provide unconfigured transform (no connect_output yet)."""
        return AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "on_error": "quarantine_sink",
            }
        )

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        return {"prompt": "What is the weather?", "id": 1}
