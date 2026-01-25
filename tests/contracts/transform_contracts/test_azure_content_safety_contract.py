# tests/contracts/transform_contracts/test_azure_content_safety_contract.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import pytest

from elspeth.plugins.context import PluginContext
from elspeth.plugins.transforms.azure.content_safety import AzureContentSafety

from .test_transform_protocol import (
    TransformContractPropertyTestBase,
    TransformErrorContractTestBase,
)

if TYPE_CHECKING:
    from elspeth.plugins.protocols import TransformProtocol


def _make_safe_response() -> dict[str, Any]:
    return {
        "categoriesAnalysis": [
            {"category": "Hate", "severity": 0},
            {"category": "Violence", "severity": 0},
            {"category": "Sexual", "severity": 0},
            {"category": "SelfHarm", "severity": 0},
        ]
    }


def _make_violation_response() -> dict[str, Any]:
    return {
        "categoriesAnalysis": [
            {"category": "Hate", "severity": 4},
            {"category": "Violence", "severity": 0},
            {"category": "Sexual", "severity": 0},
            {"category": "SelfHarm", "severity": 0},
        ]
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


class TestAzureContentSafetyContract(TransformContractPropertyTestBase):
    @pytest.fixture
    def transform(self, mock_httpx_client: Mock) -> TransformProtocol:
        mock_response = _create_mock_http_response(_make_safe_response())
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = Mock(return_value=False)
        mock_httpx_client.return_value = mock_client_instance

        transform = AzureContentSafety(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["content"],
                "thresholds": {"hate": 2, "violence": 2, "sexual": 2, "self_harm": 2},
                "schema": {"fields": "dynamic"},
                "on_error": "quarantine_sink",
            }
        )
        mock_ctx = _make_mock_context()
        transform.on_start(mock_ctx)
        return transform

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        return {"content": "Hello world", "id": 1}

    @pytest.fixture
    def ctx(self) -> Mock:
        return _make_mock_context()


class TestAzureContentSafetyErrorContract(TransformErrorContractTestBase):
    @pytest.fixture
    def transform(self, mock_httpx_client: Mock) -> TransformProtocol:
        mock_response = _create_mock_http_response(_make_violation_response())
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = Mock(return_value=False)
        mock_httpx_client.return_value = mock_client_instance

        transform = AzureContentSafety(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["content"],
                "thresholds": {"hate": 2, "violence": 2, "sexual": 2, "self_harm": 2},
                "schema": {"fields": "dynamic"},
                "on_error": "quarantine_sink",
            }
        )
        mock_ctx = _make_mock_context()
        transform.on_start(mock_ctx)
        return transform

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        return {"content": "Hello world", "id": 1}

    @pytest.fixture
    def error_input(self) -> dict[str, Any]:
        return {"content": "Hateful content", "id": 2}

    @pytest.fixture
    def ctx(self) -> Mock:
        return _make_mock_context()
