"""Tests for approved endpoint validation."""

import pytest

from elspeth.core.security import SecureMode
from elspeth.core.security.approved_endpoints import (
    get_approved_patterns,
    validate_azure_blob_endpoint,
    validate_azure_openai_endpoint,
    validate_endpoint,
    validate_http_api_endpoint,
)
from elspeth.core.validation_base import ConfigurationError


class TestEndpointValidation:
    """Test endpoint validation logic."""

    def test_azure_openai_approved_endpoint(self):
        """Test Azure OpenAI approved endpoint validation."""
        # Should pass - valid Azure OpenAI endpoint
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.com",
            security_level="OFFICIAL",
        )

    def test_azure_openai_gov_cloud(self):
        """Test Azure OpenAI Government cloud endpoint."""
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.us",
            security_level="OFFICIAL",
        )

    def test_azure_openai_china_cloud(self):
        """Test Azure OpenAI China cloud endpoint."""
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.cn",
            security_level="internal",
        )

    def test_azure_openai_unapproved_endpoint(self):
        """Test Azure OpenAI unapproved endpoint raises error."""
        with pytest.raises(ValueError, match="not approved"):
            validate_azure_openai_endpoint(
                "https://malicious-site.com",
                security_level="OFFICIAL",
            )

    def test_http_api_openai_public(self):
        """Test OpenAI public API endpoint."""
        validate_http_api_endpoint(
            "https://api.openai.com",
            security_level="public",
        )

    def test_http_api_openai_security_restriction(self):
        """Test OpenAI public API restricted for confidential data."""
        with pytest.raises(ValueError, match="not approved for security level"):
            validate_http_api_endpoint(
                "https://api.openai.com",
                security_level="confidential",
            )

    def test_http_api_localhost(self):
        """Test localhost endpoints are always allowed."""
        # HTTP localhost
        validate_http_api_endpoint("http://localhost:8080", security_level="confidential")
        validate_http_api_endpoint("http://127.0.0.1:8080", security_level="SECRET")

        # HTTPS localhost
        validate_http_api_endpoint("https://localhost:8080", security_level="confidential")
        validate_http_api_endpoint("https://127.0.0.1:8080", security_level="SECRET")

        # IPv6 localhost
        validate_http_api_endpoint("http://[::1]:8080", security_level="confidential")

    def test_http_api_unapproved_endpoint(self):
        """Test unapproved HTTP API endpoint raises error."""
        with pytest.raises(ValueError, match="not approved"):
            validate_http_api_endpoint(
                "https://evil.com/api",
                security_level="internal",
            )

    def test_azure_blob_approved_endpoints(self):
        """Test Azure Blob Storage approved endpoints."""
        # Azure public cloud
        validate_azure_blob_endpoint(
            "https://myaccount.blob.core.windows.net",
            security_level="OFFICIAL",
        )

        # Azure Government cloud
        validate_azure_blob_endpoint(
            "https://myaccount.blob.core.usgovcloudapi.net",
            security_level="OFFICIAL",
        )

        # Azure China cloud
        validate_azure_blob_endpoint(
            "https://myaccount.blob.core.chinacloudapi.cn",
            security_level="internal",
        )

    def test_azure_blob_unapproved_endpoint(self):
        """Test unapproved Azure Blob endpoint raises error."""
        with pytest.raises(ValueError, match="not approved"):
            validate_azure_blob_endpoint(
                "https://not-azure.com",
                security_level="OFFICIAL",
            )

    def test_development_mode_bypass(self):
        """Test development mode allows unapproved endpoints with warning."""
        # Should not raise in development mode
        validate_endpoint(
            endpoint="https://totally-unapproved.com",
            service_type="azure_openai",
            security_level="OFFICIAL",
            mode=SecureMode.DEVELOPMENT,
        )

    def test_standard_mode_enforcement(self):
        """Test STANDARD mode enforces endpoint validation."""
        with pytest.raises(ValueError, match="not approved"):
            validate_endpoint(
                endpoint="https://unapproved.com",
                service_type="azure_openai",
                security_level="OFFICIAL",
                mode=SecureMode.STANDARD,
            )

    def test_strict_mode_enforcement(self):
        """Test STRICT mode enforces endpoint validation."""
        with pytest.raises(ValueError, match="not approved"):
            validate_endpoint(
                endpoint="https://unapproved.com",
                service_type="azure_openai",
                security_level="OFFICIAL",
                mode=SecureMode.STRICT,
            )

    def test_endpoint_trailing_slash_normalization(self):
        """Test endpoint URLs with trailing slashes are normalized."""
        # Both should pass (trailing slash should be stripped for comparison)
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.com/",
            security_level="OFFICIAL",
        )
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.com",
            security_level="OFFICIAL",
        )

    def test_endpoint_with_path(self):
        """Test endpoints with paths are validated."""
        # Azure OpenAI endpoint with path should still match
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.com/openai/deployments/gpt-4",
            security_level="OFFICIAL",
        )

    def test_get_approved_patterns(self):
        """Test getting approved patterns for a service type."""
        patterns = get_approved_patterns("azure_openai")
        assert len(patterns) > 0
        # Patterns are regex, so check for escaped version
        assert any("openai" in p and "azure" in p for p in patterns)

        patterns = get_approved_patterns("http_api")
        assert len(patterns) > 0
        assert any("openai" in p for p in patterns)

        patterns = get_approved_patterns("azure_blob")
        assert len(patterns) > 0
        assert any("blob" in p and "windows" in p for p in patterns)

    def test_security_level_none_allowed(self):
        """Test validation works when security_level is None."""
        # Should pass without security_level
        validate_azure_openai_endpoint(
            "https://my-resource.openai.azure.com",
            security_level=None,
        )

    def test_environment_override_patterns(self, monkeypatch):
        """Test ELSPETH_APPROVED_ENDPOINTS environment variable."""
        # Add a custom approved pattern
        monkeypatch.setenv(
            "ELSPETH_APPROVED_ENDPOINTS",
            r"https://custom-llm\.internal\.company\.com(/.*)?",
        )

        # Should pass with custom pattern
        validate_http_api_endpoint(
            "https://custom-llm.internal.company.com",
            security_level="OFFICIAL",
        )

    def test_environment_override_multiple_patterns(self, monkeypatch):
        """Test multiple patterns in ELSPETH_APPROVED_ENDPOINTS."""
        monkeypatch.setenv(
            "ELSPETH_APPROVED_ENDPOINTS",
            r"https://llm1\.internal\.com(/.*)?, https://llm2\.internal\.com(/.*)?",
        )

        # Both should pass
        validate_http_api_endpoint(
            "https://llm1.internal.com",
            security_level="OFFICIAL",
        )
        validate_http_api_endpoint(
            "https://llm2.internal.com",
            security_level="OFFICIAL",
        )

    def test_ipv6_localhost(self):
        """Test IPv6 localhost addresses are allowed."""
        validate_http_api_endpoint(
            "http://[::1]:8000",
            security_level="SECRET",
        )

    def test_error_message_includes_approved_patterns(self):
        """Test error message includes approved patterns for debugging."""
        with pytest.raises(ValueError) as exc_info:
            validate_azure_openai_endpoint(
                "https://bad-endpoint.com",
                security_level="OFFICIAL",
            )

        error_msg = str(exc_info.value)
        assert "not approved" in error_msg
        assert "Approved patterns" in error_msg

    def test_openai_public_internal_allowed(self):
        """Test OpenAI public API allows public and internal security levels."""
        # public - should pass
        validate_http_api_endpoint(
            "https://api.openai.com",
            security_level="public",
        )

        # internal - should pass
        validate_http_api_endpoint(
            "https://api.openai.com",
            security_level="internal",
        )

    def test_openai_public_confidential_blocked(self):
        """Test OpenAI public API blocks confidential data."""
        with pytest.raises(ValueError, match="not approved for security level"):
            validate_http_api_endpoint(
                "https://api.openai.com",
                security_level="confidential",
            )

    def test_openai_public_restricted_blocked(self):
        """Test OpenAI public API blocks SECRET data."""
        with pytest.raises(ValueError, match="not approved for security level"):
            validate_http_api_endpoint(
                "https://api.openai.com",
                security_level="SECRET",
            )

    def test_case_insensitive_security_levels(self):
        """Test security level comparison is case-insensitive (normalized)."""
        # Security levels are normalized, so lowercase works
        validate_http_api_endpoint(
            "https://api.openai.com",
            security_level="internal",  # lowercase - normalized to OFFICIAL
        )

        validate_http_api_endpoint(
            "https://api.openai.com",
            security_level="public",  # lowercase - normalized to UNOFFICIAL
        )


class TestEndpointValidationRegistry:
    """Test endpoint validation in registry factory functions."""

    def test_azure_openai_factory_validates_endpoint(self):
        """Test Azure OpenAI factory function validates endpoints."""
        from elspeth.core.llm_registry import _create_azure_openai
        from elspeth.core.plugin_context import PluginContext
        from elspeth.core.validation_base import ConfigurationError

        context = PluginContext(
            security_level="OFFICIAL",
            plugin_kind="llm",
            plugin_name="azure_openai",
        )

        # Invalid endpoint should raise ConfigurationError during factory call
        with pytest.raises(ConfigurationError, match="endpoint validation failed"):
            _create_azure_openai(
                {
                    "config": {
                        "azure_endpoint": "https://malicious-site.com",
                        "api_key": "test-key",
                        "api_version": "2024-02-15-preview",
                    },
                    "deployment": "gpt-4",
                },
                context,
            )

    def test_http_openai_factory_validates_endpoint(self):
        """Test HTTP OpenAI factory function validates endpoints."""
        from elspeth.core.llm_registry import _create_http_openai
        from elspeth.core.plugin_context import PluginContext
        from elspeth.core.validation_base import ConfigurationError

        context = PluginContext(
            security_level="confidential",
            plugin_kind="llm",
            plugin_name="http_openai",
        )

        # OpenAI public API should be rejected for confidential data
        with pytest.raises(ConfigurationError, match="endpoint validation failed"):
            _create_http_openai(
                {
                    "api_base": "https://api.openai.com",
                    "model": "gpt-4",
                },
                context,
            )

    def test_http_openai_factory_allows_localhost(self):
        """Test HTTP OpenAI factory allows localhost endpoints."""
        from elspeth.core.llm_registry import _create_http_openai
        from elspeth.core.plugin_context import PluginContext

        context = PluginContext(
            security_level="SECRET",
            plugin_kind="llm",
            plugin_name="http_openai",
        )

        # Localhost should work for any security level - validation passes
        # We don't actually create the client (would require openai package)
        # We just test that validation passes
        try:
            _create_http_openai(
                {
                    "api_base": "http://localhost:8000",
                    "model": "llama-2",
                },
                context,
            )
        except ConfigurationError as exc:
            # Should not raise ConfigurationError for endpoint validation
            if "endpoint validation failed" in str(exc):
                pytest.fail("Localhost endpoint should be allowed")
