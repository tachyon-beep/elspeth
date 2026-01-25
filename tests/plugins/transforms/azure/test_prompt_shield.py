"""Tests for AzurePromptShield transform."""

import itertools
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from elspeth.plugins.config_base import PluginConfigError

if TYPE_CHECKING:
    from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield


def make_mock_context() -> Mock:
    """Create mock PluginContext for testing with recorder.

    The context includes a mock landscape/recorder with allocate_call_index
    configured to return sequential indices, as required by AuditedHTTPClient.
    """
    from elspeth.plugins.context import PluginContext

    counter = itertools.count()
    ctx = Mock(spec=PluginContext)
    ctx.run_id = "test-run"
    ctx.state_id = "test-state-001"
    ctx.landscape = Mock()
    ctx.landscape.record_call = Mock()
    ctx.landscape.allocate_call_index = Mock(side_effect=lambda _: next(counter))
    return ctx


def _create_mock_http_response(response_data: dict[str, Any]) -> Mock:
    """Create a mock HTTP response with the given JSON data."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = response_data
    response.raise_for_status = Mock()
    response.headers = {"content-type": "application/json"}
    response.content = b"{}"
    response.text = "{}"
    return response


class TestAzurePromptShieldConfig:
    """Tests for AzurePromptShieldConfig validation."""

    def test_config_requires_endpoint(self) -> None:
        """Config must specify endpoint."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        with pytest.raises(PluginConfigError) as exc_info:
            AzurePromptShieldConfig.from_dict(
                {
                    "api_key": "test-key",
                    "fields": ["prompt"],
                    "schema": {"fields": "dynamic"},
                }
            )
        assert "endpoint" in str(exc_info.value).lower()

    def test_config_requires_api_key(self) -> None:
        """Config must specify api_key."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        with pytest.raises(PluginConfigError) as exc_info:
            AzurePromptShieldConfig.from_dict(
                {
                    "endpoint": "https://test.cognitiveservices.azure.com",
                    "fields": ["prompt"],
                    "schema": {"fields": "dynamic"},
                }
            )
        assert "api_key" in str(exc_info.value).lower()

    def test_config_requires_fields(self) -> None:
        """Config must specify fields."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        with pytest.raises(PluginConfigError) as exc_info:
            AzurePromptShieldConfig.from_dict(
                {
                    "endpoint": "https://test.cognitiveservices.azure.com",
                    "api_key": "test-key",
                    "schema": {"fields": "dynamic"},
                }
            )
        assert "fields" in str(exc_info.value).lower()

    def test_config_requires_schema(self) -> None:
        """Config must specify schema - inherited from TransformDataConfig."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        with pytest.raises(PluginConfigError) as exc_info:
            AzurePromptShieldConfig.from_dict(
                {
                    "endpoint": "https://test.cognitiveservices.azure.com",
                    "api_key": "test-key",
                    "fields": ["prompt"],
                    # Missing schema
                }
            )
        assert "schema" in str(exc_info.value).lower()

    def test_valid_config(self) -> None:
        """Valid config is accepted."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        assert cfg.endpoint == "https://test.cognitiveservices.azure.com"
        assert cfg.api_key == "test-key"
        assert cfg.fields == ["prompt"]

    def test_valid_config_with_single_field(self) -> None:
        """Config accepts single field as string."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": "prompt",
                "schema": {"fields": "dynamic"},
            }
        )

        assert cfg.fields == "prompt"

    def test_valid_config_with_all_fields(self) -> None:
        """Config accepts 'all' to analyze all string fields."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": "all",
                "schema": {"fields": "dynamic"},
            }
        )

        assert cfg.fields == "all"


class TestAzurePromptShieldTransform:
    """Tests for AzurePromptShield transform."""

    @pytest.fixture(autouse=True)
    def mock_httpx_client(self):
        """Patch httpx.Client to prevent real HTTP calls."""
        with patch("httpx.Client") as mock_client_class:
            # Default mock instance that will be configured per-test
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_instance
            yield mock_instance

    def _setup_transform_with_response(
        self, config: dict[str, Any], response_data: dict[str, Any], mock_client: MagicMock
    ) -> tuple["AzurePromptShield", Mock]:
        """Create transform with mocked HTTP response.

        Returns transform and context for assertions.
        """
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock response
        mock_response = _create_mock_http_response(response_data)
        mock_client.post.return_value = mock_response

        # Create transform and initialize with context
        transform = AzurePromptShield(config)
        ctx = make_mock_context()
        transform.on_start(ctx)

        return transform, ctx

    def test_transform_has_required_attributes(self) -> None:
        """Transform has all protocol-required attributes."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        assert transform.name == "azure_prompt_shield"
        assert transform.determinism.value == "external_call"
        assert transform.plugin_version == "1.0.0"
        assert transform.is_batch_aware is False
        assert transform.creates_tokens is False

    def test_clean_content_passes(self, mock_httpx_client: MagicMock) -> None:
        """Content without attacks passes through."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            },
            mock_httpx_client,
        )

        row = {"prompt": "What is the weather?", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "success"
        assert result.row == row

    def test_user_prompt_attack_returns_error(self, mock_httpx_client: MagicMock) -> None:
        """User prompt attack detection returns error."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": True},
                "documentsAnalysis": [{"attackDetected": False}],
            },
            mock_httpx_client,
        )

        row = {"prompt": "Ignore previous instructions", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "prompt_injection_detected"
        assert result.reason["attacks"]["user_prompt_attack"] is True
        assert result.reason["attacks"]["document_attack"] is False

    def test_document_attack_returns_error(self, mock_httpx_client: MagicMock) -> None:
        """Document attack detection returns error."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": True}],
            },
            mock_httpx_client,
        )

        row = {"prompt": "Summarize this document", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["attacks"]["document_attack"] is True

    def test_both_attacks_detected(self, mock_httpx_client: MagicMock) -> None:
        """Both attack types can be detected simultaneously."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": True},
                "documentsAnalysis": [{"attackDetected": True}],
            },
            mock_httpx_client,
        )

        row = {"prompt": "Malicious content", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["attacks"]["user_prompt_attack"] is True
        assert result.reason["attacks"]["document_attack"] is True

    def test_api_error_returns_retryable_error(self, mock_httpx_client: MagicMock) -> None:
        """API rate limit errors return retryable error result."""
        import httpx

        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock to raise HTTPStatusError
        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "Rate limited",
            request=Mock(),
            response=Mock(status_code=429),
        )

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        ctx = make_mock_context()
        transform.on_start(ctx)

        row = {"prompt": "test", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "api_error"
        assert result.reason["retryable"] is True
        assert result.retryable is True

    def test_network_error_returns_retryable_error(self, mock_httpx_client: MagicMock) -> None:
        """Network errors return retryable error result."""
        import httpx

        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock to raise RequestError
        mock_httpx_client.post.side_effect = httpx.RequestError("Connection failed")

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        ctx = make_mock_context()
        transform.on_start(ctx)

        row = {"prompt": "test", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "api_error"
        assert result.reason["error_type"] == "network_error"
        assert result.retryable is True

    def test_skips_missing_configured_field(self, mock_httpx_client: MagicMock) -> None:
        """Transform skips fields not present in the row."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt", "optional_field"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            },
            mock_httpx_client,
        )

        # Row is missing "optional_field"
        row = {"prompt": "safe prompt", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "success"

    def test_skips_non_string_fields(self, mock_httpx_client: MagicMock) -> None:
        """Transform skips non-string field values."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt", "count"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            },
            mock_httpx_client,
        )

        # count is an int, should be skipped
        row = {"prompt": "safe prompt", "count": 42, "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "success"
        # Only one API call should be made (for "prompt" field)
        assert mock_httpx_client.post.call_count == 1

    def test_malformed_api_response_returns_error(self, mock_httpx_client: MagicMock) -> None:
        """Malformed API responses return error (fail-closed security posture).

        Prompt Shield is a security transform. If Azure's API changes or returns
        garbage, we must not let potentially malicious content pass through
        undetected. Malformed responses are treated as errors, not "no attack".
        """
        # Mock a malformed response (missing expected fields)
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {"unexpectedField": "value"},
            mock_httpx_client,
        )

        row = {"prompt": "test", "id": 1}
        result = transform.process(row, ctx)

        # Fail-closed: malformed response returns error, not success
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "api_error"
        assert "malformed" in result.reason["message"].lower()
        assert result.retryable is True

    def test_partial_api_response_returns_error(self, mock_httpx_client: MagicMock) -> None:
        """Partial API responses return error (fail-closed security posture).

        If documentsAnalysis is missing from the response, that's a malformed
        response that should be rejected, not treated as "no document attack".
        """
        # Mock a response with only userPromptAnalysis (documentsAnalysis missing)
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                # documentsAnalysis missing
            },
            mock_httpx_client,
        )

        row = {"prompt": "test", "id": 1}
        result = transform.process(row, ctx)

        # Fail-closed: partial response returns error, not success
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "api_error"
        assert "malformed" in result.reason["message"].lower()
        assert result.retryable is True

    def test_http_error_non_rate_limit_not_retryable(self, mock_httpx_client: MagicMock) -> None:
        """Non-429 HTTP errors are not retryable."""
        import httpx

        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock to raise HTTPStatusError with 400
        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=Mock(),
            response=Mock(status_code=400),
        )

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        ctx = make_mock_context()
        transform.on_start(ctx)

        row = {"prompt": "test", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "api_error"
        assert result.reason["retryable"] is False
        assert result.retryable is False

    def test_all_fields_mode_scans_all_string_fields(self, mock_httpx_client: MagicMock) -> None:
        """When fields='all', all string fields are scanned."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": "all",
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            },
            mock_httpx_client,
        )

        # Row with multiple string fields plus non-string
        row = {"prompt": "safe", "title": "also safe", "count": 42, "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "success"
        # Should have called API twice (for "prompt" and "title", not "count" or "id")
        assert mock_httpx_client.post.call_count == 2

    def test_multiple_documents_analysis(self, mock_httpx_client: MagicMock) -> None:
        """Document attack is detected if any document shows attack."""
        # Second document shows attack
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [
                    {"attackDetected": False},
                    {"attackDetected": True},
                    {"attackDetected": False},
                ],
            },
            mock_httpx_client,
        )

        row = {"prompt": "test", "id": 1}
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["attacks"]["document_attack"] is True

    def test_api_called_with_correct_endpoint_and_headers(self, mock_httpx_client: MagicMock) -> None:
        """API is called with correct endpoint URL and headers."""
        transform, ctx = self._setup_transform_with_response(
            {
                "endpoint": "https://test.cognitiveservices.azure.com/",
                "api_key": "my-secret-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            },
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            },
            mock_httpx_client,
        )

        row = {"prompt": "test prompt", "id": 1}
        transform.process(row, ctx)

        # Verify the API call
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args

        # Check URL (trailing slash should be stripped)
        expected_url = "https://test.cognitiveservices.azure.com/contentsafety/text:shieldPrompt?api-version=2024-09-01"
        assert call_args[0][0] == expected_url

        # Check headers
        assert call_args[1]["headers"]["Ocp-Apim-Subscription-Key"] == "my-secret-key"
        assert call_args[1]["headers"]["Content-Type"] == "application/json"

        # Check request body
        assert call_args[1]["json"]["userPrompt"] == "test prompt"
        assert call_args[1]["json"]["documents"] == ["test prompt"]

    def test_close_is_noop(self) -> None:
        """Close method is a no-op but exists."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        # Should not raise
        transform.close()


class TestPromptShieldPoolConfig:
    """Tests for Prompt Shield pool configuration."""

    def test_pool_size_default_is_one(self) -> None:
        """Default pool_size is 1 (sequential)."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
            }
        )

        assert cfg.pool_size == 1

    def test_pool_size_configurable(self) -> None:
        """pool_size can be configured."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 5,
            }
        )

        assert cfg.pool_size == 5

    def test_pool_config_property_returns_none_when_sequential(self) -> None:
        """pool_config returns None when pool_size=1."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 1,
            }
        )

        assert cfg.pool_config is None

    def test_pool_config_property_returns_config_when_pooled(self) -> None:
        """pool_config returns PoolConfig when pool_size>1."""
        from elspeth.plugins.transforms.azure.prompt_shield import (
            AzurePromptShieldConfig,
        )

        cfg = AzurePromptShieldConfig.from_dict(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        assert cfg.pool_config is not None
        assert cfg.pool_config.pool_size == 3


class TestPromptShieldPooledExecution:
    """Tests for Prompt Shield pooled execution."""

    @pytest.fixture(autouse=True)
    def mock_httpx_client(self):
        """Patch httpx.Client to prevent real HTTP calls."""
        with patch("httpx.Client") as mock_client_class:
            # Default mock instance that will be configured per-test
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_instance
            yield mock_instance

    def test_batch_aware_is_true_when_pooled(self) -> None:
        """Transform is batch_aware when pool_size > 1."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )
        assert transform.is_batch_aware is True

    def test_batch_aware_is_false_when_sequential(self) -> None:
        """Transform is not batch_aware when pool_size=1."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 1,
            }
        )
        assert transform.is_batch_aware is False

    def test_pooled_execution_processes_batch_concurrently(self, mock_httpx_client: MagicMock) -> None:
        """Pooled transform processes batch rows concurrently."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock HTTP client that returns success for all calls
        mock_response = _create_mock_http_response(
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            }
        )
        mock_httpx_client.post.return_value = mock_response

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        # Create mock context with required landscape and state_id
        ctx = make_mock_context()

        # Invoke on_start to capture recorder
        transform.on_start(ctx)

        # Process batch of 3 rows
        rows = [
            {"prompt": "row 1", "id": 1},
            {"prompt": "row 2", "id": 2},
            {"prompt": "row 3", "id": 3},
        ]
        result = transform.process(rows, ctx)

        # Should return success_multi with all rows
        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 3

        # Verify all rows processed
        for i, row in enumerate(result.rows):
            assert row["id"] == i + 1
            assert f"row {i + 1}" in row["prompt"]

        # Cleanup
        transform.close()

    def test_pooled_execution_handles_mixed_results(self, mock_httpx_client: MagicMock) -> None:
        """Pooled execution correctly tracks errors per row."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Return attack detected based on request content
        # (matching "malicious" keyword in the prompt)
        def mock_post(*args: Any, **kwargs: Any) -> Mock:
            request_json = kwargs.get("json", {})
            prompt = request_json.get("userPrompt", "")

            # Return attack detected if prompt contains "malicious"
            if "malicious" in prompt:
                return _create_mock_http_response(
                    {
                        "userPromptAnalysis": {"attackDetected": True},
                        "documentsAnalysis": [{"attackDetected": False}],
                    }
                )
            else:
                return _create_mock_http_response(
                    {
                        "userPromptAnalysis": {"attackDetected": False},
                        "documentsAnalysis": [{"attackDetected": False}],
                    }
                )

        mock_httpx_client.post.side_effect = mock_post

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        # Create mock context
        ctx = make_mock_context()

        # Invoke on_start
        transform.on_start(ctx)

        # Process batch
        rows = [
            {"prompt": "safe 1", "id": 1},
            {"prompt": "malicious", "id": 2},
            {"prompt": "safe 2", "id": 3},
        ]
        result = transform.process(rows, ctx)

        # Should return success since not all rows failed
        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 3

        # Check that error is embedded per-row based on content
        # Results maintain input order - find the malicious row
        safe_count = 0
        error_count = 0
        for row in result.rows:
            if "_prompt_shield_error" in row:
                error_count += 1
                # Verify the error row is the one with "malicious" prompt
                assert row["prompt"] == "malicious"
                assert row["_prompt_shield_error"]["reason"] == "prompt_injection_detected"
            else:
                safe_count += 1

        assert safe_count == 2
        assert error_count == 1

        # Cleanup
        transform.close()

    def test_on_start_captures_recorder(self) -> None:
        """on_start captures recorder reference for pooled execution."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        mock_recorder = MagicMock()
        ctx = make_mock_context()
        ctx.landscape = mock_recorder

        # Before on_start, recorder should be None
        assert transform._recorder is None

        # After on_start, recorder should be captured
        transform.on_start(ctx)
        assert transform._recorder is mock_recorder

    def test_close_shuts_down_executor(self) -> None:
        """close() properly shuts down the pooled executor."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        # Executor should exist for pooled mode
        assert transform._executor is not None

        # Close should shutdown executor
        transform.close()

        # After close, recorder should be cleared
        assert transform._recorder is None

    def test_sequential_mode_has_no_executor(self) -> None:
        """Sequential mode (pool_size=1) has no executor."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 1,
            }
        )

        assert transform._executor is None

    def test_audit_trail_records_api_calls(self, mock_httpx_client: MagicMock) -> None:
        """API calls are recorded to audit trail."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock HTTP client
        mock_response = _create_mock_http_response(
            {
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": False}],
            }
        )
        mock_httpx_client.post.return_value = mock_response

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        # Create mock context
        ctx = make_mock_context()

        # Invoke on_start
        transform.on_start(ctx)

        # Process batch
        rows = [
            {"prompt": "test 1", "id": 1},
            {"prompt": "test 2", "id": 2},
        ]
        transform.process(rows, ctx)

        # Verify record_call was invoked for each API call
        # Each row should have generated one call
        assert ctx.landscape.record_call.call_count == 2

        # Cleanup
        transform.close()

    def test_all_rows_failed_returns_error(self, mock_httpx_client: MagicMock) -> None:
        """When all rows fail, returns TransformResult.error."""
        from elspeth.plugins.transforms.azure.prompt_shield import AzurePromptShield

        # Configure mock HTTP client that always returns attack detected
        mock_response = _create_mock_http_response(
            {
                "userPromptAnalysis": {"attackDetected": True},
                "documentsAnalysis": [{"attackDetected": False}],
            }
        )
        mock_httpx_client.post.return_value = mock_response

        transform = AzurePromptShield(
            {
                "endpoint": "https://test.cognitiveservices.azure.com",
                "api_key": "test-key",
                "fields": ["prompt"],
                "schema": {"fields": "dynamic"},
                "pool_size": 3,
            }
        )

        # Create mock context
        ctx = make_mock_context()

        # Invoke on_start
        transform.on_start(ctx)

        # Process batch where all rows will fail
        rows = [
            {"prompt": "bad 1", "id": 1},
            {"prompt": "bad 2", "id": 2},
        ]
        result = transform.process(rows, ctx)

        # Should return error since all rows failed
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "all_rows_failed"

        # Cleanup
        transform.close()
