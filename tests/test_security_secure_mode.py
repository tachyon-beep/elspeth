"""Tests for secure mode detection and validation."""


import pytest

from elspeth.core.security.secure_mode import (
    SecureMode,
    get_mode_description,
    get_secure_mode,
    is_development_mode,
    is_strict_mode,
    validate_datasource_config,
    validate_llm_config,
    validate_middleware_config,
    validate_sink_config,
)


class TestSecureModeDetection:
    """Test secure mode environment detection."""

    def test_from_environment_strict(self, monkeypatch):
        """Test STRICT mode detection from environment."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "strict")
        assert SecureMode.from_environment() == SecureMode.STRICT

    def test_from_environment_standard(self, monkeypatch):
        """Test STANDARD mode detection (default)."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "standard")
        assert SecureMode.from_environment() == SecureMode.STANDARD

    def test_from_environment_development(self, monkeypatch):
        """Test DEVELOPMENT mode detection."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "development")
        assert SecureMode.from_environment() == SecureMode.DEVELOPMENT

    def test_from_environment_case_insensitive(self, monkeypatch):
        """Test case-insensitive mode detection."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "STRICT")
        assert SecureMode.from_environment() == SecureMode.STRICT

    def test_from_environment_default(self, monkeypatch):
        """Test default mode when environment variable not set."""
        monkeypatch.delenv("ELSPETH_SECURE_MODE", raising=False)
        assert SecureMode.from_environment() == SecureMode.STANDARD

    def test_from_environment_invalid(self, monkeypatch):
        """Test invalid mode falls back to STANDARD."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "invalid")
        assert SecureMode.from_environment() == SecureMode.STANDARD

    def test_get_secure_mode(self, monkeypatch):
        """Test get_secure_mode() helper."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "strict")
        assert get_secure_mode() == SecureMode.STRICT

    def test_is_strict_mode(self, monkeypatch):
        """Test is_strict_mode() helper."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "strict")
        assert is_strict_mode() is True

        monkeypatch.setenv("ELSPETH_SECURE_MODE", "standard")
        assert is_strict_mode() is False

    def test_is_development_mode(self, monkeypatch):
        """Test is_development_mode() helper."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "development")
        assert is_development_mode() is True

        monkeypatch.setenv("ELSPETH_SECURE_MODE", "standard")
        assert is_development_mode() is False


class TestDatasourceValidation:
    """Test datasource configuration validation."""

    def test_datasource_strict_requires_security_level(self):
        """Test STRICT mode requires security_level."""
        config = {"type": "local_csv", "path": "data.csv", "retain_local": True}

        with pytest.raises(ValueError, match="missing required 'security_level'"):
            validate_datasource_config(config, mode=SecureMode.STRICT)

    def test_datasource_standard_requires_security_level(self):
        """Test STANDARD mode requires security_level."""
        config = {"type": "local_csv", "path": "data.csv"}

        with pytest.raises(ValueError, match="missing required 'security_level'"):
            validate_datasource_config(config, mode=SecureMode.STANDARD)

    def test_datasource_development_allows_missing_security_level(self):
        """Test DEVELOPMENT mode allows missing security_level."""
        config = {"type": "local_csv", "path": "data.csv"}

        # Should not raise
        validate_datasource_config(config, mode=SecureMode.DEVELOPMENT)

    def test_datasource_strict_requires_retain_local(self):
        """Test STRICT mode requires retain_local=True."""
        config = {
            "type": "local_csv",
            "path": "data.csv",
            "security_level": "OFFICIAL",
            "retain_local": False,
        }

        with pytest.raises(ValueError, match="retain_local=False which violates STRICT mode"):
            validate_datasource_config(config, mode=SecureMode.STRICT)

    def test_datasource_strict_allows_retain_local_true(self):
        """Test STRICT mode allows retain_local=True."""
        config = {
            "type": "local_csv",
            "path": "data.csv",
            "security_level": "OFFICIAL",
            "retain_local": True,
        }

        # Should not raise
        validate_datasource_config(config, mode=SecureMode.STRICT)

    def test_datasource_standard_warns_retain_local_false(self):
        """Test STANDARD mode warns about retain_local=False."""
        config = {
            "type": "local_csv",
            "path": "data.csv",
            "security_level": "OFFICIAL",
            "retain_local": False,
        }

        # Should not raise, but logs warning
        validate_datasource_config(config, mode=SecureMode.STANDARD)

    def test_datasource_development_allows_retain_local_false(self):
        """Test DEVELOPMENT mode allows retain_local=False."""
        config = {
            "type": "local_csv",
            "path": "data.csv",
            "retain_local": False,
        }

        # Should not raise
        validate_datasource_config(config, mode=SecureMode.DEVELOPMENT)


class TestLLMValidation:
    """Test LLM configuration validation."""

    def test_llm_strict_requires_security_level(self):
        """Test STRICT mode requires security_level."""
        config = {"type": "azure_openai", "endpoint": "https://api.openai.com"}

        with pytest.raises(ValueError, match="missing required 'security_level'"):
            validate_llm_config(config, mode=SecureMode.STRICT)

    def test_llm_standard_requires_security_level(self):
        """Test STANDARD mode requires security_level."""
        config = {"type": "azure_openai", "endpoint": "https://api.openai.com"}

        with pytest.raises(ValueError, match="missing required 'security_level'"):
            validate_llm_config(config, mode=SecureMode.STANDARD)

    def test_llm_development_allows_missing_security_level(self):
        """Test DEVELOPMENT mode allows missing security_level."""
        config = {"type": "azure_openai", "endpoint": "https://api.openai.com"}

        # Should not raise
        validate_llm_config(config, mode=SecureMode.DEVELOPMENT)

    def test_llm_strict_disallows_mock(self):
        """Test STRICT mode disallows mock LLMs."""
        config = {"type": "mock", "security_level": "OFFICIAL"}

        with pytest.raises(ValueError, match="not allowed in STRICT mode"):
            validate_llm_config(config, mode=SecureMode.STRICT)

    def test_llm_strict_disallows_static_test(self):
        """Test STRICT mode disallows static_test LLMs."""
        config = {"type": "static_test", "content": "test", "security_level": "OFFICIAL"}

        with pytest.raises(ValueError, match="not allowed in STRICT mode"):
            validate_llm_config(config, mode=SecureMode.STRICT)

    def test_llm_standard_warns_mock(self):
        """Test STANDARD mode warns about mock LLMs."""
        config = {"type": "mock", "security_level": "OFFICIAL"}

        # Should not raise, but logs warning
        validate_llm_config(config, mode=SecureMode.STANDARD)

    def test_llm_development_allows_mock(self):
        """Test DEVELOPMENT mode allows mock LLMs."""
        config = {"type": "mock"}

        # Should not raise
        validate_llm_config(config, mode=SecureMode.DEVELOPMENT)

    def test_llm_strict_allows_real_llm(self):
        """Test STRICT mode allows real LLMs."""
        config = {"type": "azure_openai", "endpoint": "https://api.openai.com", "security_level": "OFFICIAL"}

        # Should not raise
        validate_llm_config(config, mode=SecureMode.STRICT)


class TestSinkValidation:
    """Test sink configuration validation."""

    def test_sink_strict_requires_security_level(self):
        """Test STRICT mode requires security_level."""
        config = {"type": "csv", "path": "output.csv"}

        with pytest.raises(ValueError, match="missing required 'security_level'"):
            validate_sink_config(config, mode=SecureMode.STRICT)

    def test_sink_standard_requires_security_level(self):
        """Test STANDARD mode requires security_level."""
        config = {"type": "csv", "path": "output.csv"}

        with pytest.raises(ValueError, match="missing required 'security_level'"):
            validate_sink_config(config, mode=SecureMode.STANDARD)

    def test_sink_development_allows_missing_security_level(self):
        """Test DEVELOPMENT mode allows missing security_level."""
        config = {"type": "csv", "path": "output.csv"}

        # Should not raise
        validate_sink_config(config, mode=SecureMode.DEVELOPMENT)

    def test_sink_strict_requires_formula_sanitization(self):
        """Test STRICT mode requires formula sanitization."""
        config = {
            "type": "csv",
            "path": "output.csv",
            "security_level": "OFFICIAL",
            "sanitize_formulas": False,
        }

        with pytest.raises(ValueError, match="sanitize_formulas=False which violates STRICT mode"):
            validate_sink_config(config, mode=SecureMode.STRICT)

    def test_sink_strict_allows_formula_sanitization_enabled(self):
        """Test STRICT mode allows sanitize_formulas=True."""
        config = {
            "type": "csv",
            "path": "output.csv",
            "security_level": "OFFICIAL",
            "sanitize_formulas": True,
        }

        # Should not raise
        validate_sink_config(config, mode=SecureMode.STRICT)

    def test_sink_strict_defaults_formula_sanitization(self):
        """Test STRICT mode accepts default formula sanitization."""
        config = {
            "type": "csv",
            "path": "output.csv",
            "security_level": "OFFICIAL",
            # sanitize_formulas not specified, defaults to True
        }

        # Should not raise
        validate_sink_config(config, mode=SecureMode.STRICT)

    def test_sink_standard_warns_formula_sanitization_disabled(self):
        """Test STANDARD mode warns about sanitize_formulas=False."""
        config = {
            "type": "csv",
            "path": "output.csv",
            "security_level": "OFFICIAL",
            "sanitize_formulas": False,
        }

        # Should not raise, but logs warning
        validate_sink_config(config, mode=SecureMode.STANDARD)

    def test_sink_development_allows_formula_sanitization_disabled(self):
        """Test DEVELOPMENT mode allows sanitize_formulas=False."""
        config = {
            "type": "csv",
            "path": "output.csv",
            "sanitize_formulas": False,
        }

        # Should not raise
        validate_sink_config(config, mode=SecureMode.DEVELOPMENT)

    def test_sink_formula_validation_for_csv_types(self):
        """Test formula validation applies to CSV, Excel, bundle sinks."""
        csv_types = ["csv", "excel_workbook", "local_bundle", "zip_bundle"]

        for sink_type in csv_types:
            config = {
                "type": sink_type,
                "path": "output",
                "security_level": "OFFICIAL",
                "sanitize_formulas": False,
            }

            with pytest.raises(ValueError, match="sanitize_formulas=False which violates STRICT mode"):
                validate_sink_config(config, mode=SecureMode.STRICT)

    def test_sink_formula_validation_skipped_for_other_types(self):
        """Test formula validation skipped for non-CSV/Excel sinks."""
        config = {
            "type": "azure_blob",
            "container": "outputs",
            "security_level": "OFFICIAL",
            # sanitize_formulas not relevant for this sink type
        }

        # Should not raise
        validate_sink_config(config, mode=SecureMode.STRICT)


class TestMiddlewareValidation:
    """Test middleware configuration validation."""

    def test_middleware_strict_warns_missing_audit(self):
        """Test STRICT mode warns when audit_logger middleware missing."""
        middleware = [{"type": "prompt_shield", "enabled": True}]

        # Should not raise, but logs warning
        validate_middleware_config(middleware, mode=SecureMode.STRICT)

    def test_middleware_strict_accepts_audit_logger(self):
        """Test STRICT mode accepts audit_logger middleware."""
        middleware = [
            {"type": "audit_logger", "enabled": True},
            {"type": "prompt_shield", "enabled": True},
        ]

        # Should not raise
        validate_middleware_config(middleware, mode=SecureMode.STRICT)

    def test_middleware_standard_no_requirements(self):
        """Test STANDARD mode has no middleware requirements."""
        middleware = [{"type": "prompt_shield", "enabled": True}]

        # Should not raise
        validate_middleware_config(middleware, mode=SecureMode.STANDARD)

    def test_middleware_development_no_requirements(self):
        """Test DEVELOPMENT mode has no middleware requirements."""
        middleware = []

        # Should not raise
        validate_middleware_config(middleware, mode=SecureMode.DEVELOPMENT)


class TestModeDescription:
    """Test secure mode description helper."""

    def test_get_mode_description_strict(self):
        """Test description for STRICT mode."""
        desc = get_mode_description(SecureMode.STRICT)
        assert "STRICT mode" in desc
        assert "security_level REQUIRED" in desc
        assert "retain_local REQUIRED" in desc

    def test_get_mode_description_standard(self):
        """Test description for STANDARD mode."""
        desc = get_mode_description(SecureMode.STANDARD)
        assert "STANDARD mode" in desc
        assert "security_level REQUIRED" in desc

    def test_get_mode_description_development(self):
        """Test description for DEVELOPMENT mode."""
        desc = get_mode_description(SecureMode.DEVELOPMENT)
        assert "DEVELOPMENT mode" in desc
        assert "OPTIONAL" in desc

    def test_get_mode_description_auto_detect(self, monkeypatch):
        """Test description auto-detects mode from environment."""
        monkeypatch.setenv("ELSPETH_SECURE_MODE", "strict")
        desc = get_mode_description()
        assert "STRICT mode" in desc
