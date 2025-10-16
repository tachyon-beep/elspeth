"""Tests for configuration validation guards."""

import pytest

from elspeth.core.config_validation import (
    validate_full_configuration,
    validate_plugin_definition,
    validate_prompt_pack,
    validate_suite_configuration,
)
from elspeth.core.security.secure_mode import SecureMode
from elspeth.core.validation_base import ConfigurationError


class TestFullConfigurationValidation:
    """Test full configuration validation."""

    def test_valid_configuration_standard_mode(self):
        """Test valid configuration in STANDARD mode."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
                "retain_local": True,
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
            "sinks": [
                {
                    "type": "csv",
                    "path": "output.csv",
                    "security_level": "OFFICIAL",
                }
            ],
        }

        # Should not raise
        validate_full_configuration(config, mode=SecureMode.STANDARD)

    def test_missing_datasource_security_level_standard(self):
        """Test missing datasource security_level in STANDARD mode raises error."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
        }

        with pytest.raises(ConfigurationError, match="Datasource validation failed"):
            validate_full_configuration(config, mode=SecureMode.STANDARD)

    def test_missing_llm_security_level_standard(self):
        """Test missing LLM security_level in STANDARD mode raises error."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
            },
        }

        with pytest.raises(ConfigurationError, match="LLM validation failed"):
            validate_full_configuration(config, mode=SecureMode.STANDARD)

    def test_missing_sink_security_level_standard(self):
        """Test missing sink security_level in STANDARD mode raises error."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
            "sinks": [
                {
                    "type": "csv",
                    "path": "output.csv",
                }
            ],
        }

        with pytest.raises(ConfigurationError, match="Sink\\[0\\] validation failed"):
            validate_full_configuration(config, mode=SecureMode.STANDARD)

    def test_development_mode_allows_missing_security_levels(self):
        """Test DEVELOPMENT mode allows missing security_level."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
            },
            "sinks": [
                {
                    "type": "csv",
                    "path": "output.csv",
                }
            ],
        }

        # Should not raise
        validate_full_configuration(config, mode=SecureMode.DEVELOPMENT)

    def test_strict_mode_disallows_mock_llm(self):
        """Test STRICT mode disallows mock LLMs."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
                "retain_local": True,
            },
            "llm": {
                "type": "mock",
                "security_level": "OFFICIAL",
            },
        }

        with pytest.raises(ConfigurationError, match="LLM validation failed.*not allowed in STRICT mode"):
            validate_full_configuration(config, mode=SecureMode.STRICT)

    def test_strict_mode_requires_retain_local(self):
        """Test STRICT mode requires retain_local=True."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
                "retain_local": False,
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
        }

        with pytest.raises(ConfigurationError, match="Datasource validation failed.*retain_local=False which violates STRICT mode"):
            validate_full_configuration(config, mode=SecureMode.STRICT)

    def test_strict_mode_requires_formula_sanitization(self):
        """Test STRICT mode requires formula sanitization."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
                "retain_local": True,
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
            "sinks": [
                {
                    "type": "csv",
                    "path": "output.csv",
                    "security_level": "OFFICIAL",
                    "sanitize_formulas": False,
                }
            ],
        }

        with pytest.raises(ConfigurationError, match="Sink\\[0\\] validation failed.*sanitize_formulas=False which violates STRICT mode"):
            validate_full_configuration(config, mode=SecureMode.STRICT)

    def test_middleware_validation(self):
        """Test middleware configuration validation."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
            "llm_middlewares": [
                {"type": "prompt_shield", "enabled": True},
            ],
        }

        # Should not raise (middleware validation is mostly warnings)
        validate_full_configuration(config, mode=SecureMode.STRICT)

    def test_invalid_datasource_type(self):
        """Test non-mapping datasource configuration raises error."""
        config = {
            "datasource": "invalid",
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
        }

        with pytest.raises(ConfigurationError, match="Datasource configuration must be a mapping"):
            validate_full_configuration(config, mode=SecureMode.STANDARD)

    def test_invalid_llm_type(self):
        """Test non-mapping LLM configuration raises error."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
            },
            "llm": "invalid",
        }

        with pytest.raises(ConfigurationError, match="LLM configuration must be a mapping"):
            validate_full_configuration(config, mode=SecureMode.STANDARD)

    def test_invalid_sink_type(self):
        """Test non-mapping sink configuration raises error."""
        config = {
            "datasource": {
                "type": "local_csv",
                "path": "data.csv",
                "security_level": "OFFICIAL",
            },
            "llm": {
                "type": "azure_openai",
                "endpoint": "https://api.openai.com",
                "security_level": "OFFICIAL",
            },
            "sinks": ["invalid"],
        }

        with pytest.raises(ConfigurationError, match="Sink\\[0\\] configuration must be a mapping"):
            validate_full_configuration(config, mode=SecureMode.STANDARD)


class TestPluginDefinitionValidation:
    """Test individual plugin definition validation."""

    def test_validate_datasource_plugin(self):
        """Test datasource plugin definition validation."""
        definition = {
            "type": "local_csv",
            "path": "data.csv",
            "security_level": "OFFICIAL",
            "retain_local": True,
        }

        # Should not raise
        validate_plugin_definition(definition, "datasource", mode=SecureMode.STANDARD)

    def test_validate_llm_plugin(self):
        """Test LLM plugin definition validation."""
        definition = {
            "type": "azure_openai",
            "endpoint": "https://api.openai.com",
            "security_level": "OFFICIAL",
        }

        # Should not raise
        validate_plugin_definition(definition, "llm", mode=SecureMode.STANDARD)

    def test_validate_sink_plugin(self):
        """Test sink plugin definition validation."""
        definition = {
            "type": "csv",
            "path": "output.csv",
            "security_level": "OFFICIAL",
        }

        # Should not raise
        validate_plugin_definition(definition, "sink", mode=SecureMode.STANDARD)

    def test_validate_plugin_with_options(self):
        """Test plugin definition with separate options block."""
        definition = {
            "plugin": "local_csv",
            "options": {
                "path": "data.csv",
                "security_level": "OFFICIAL",
                "retain_local": True,
            },
        }

        # Should not raise (merged config validated)
        validate_plugin_definition(definition, "datasource", mode=SecureMode.STANDARD)

    def test_validate_unknown_plugin_type(self):
        """Test unknown plugin type logs debug message."""
        definition = {
            "type": "unknown",
            "some_option": "value",
        }

        # Should not raise (no specific validation)
        validate_plugin_definition(definition, "unknown", mode=SecureMode.STANDARD)

    def test_validate_plugin_missing_security_level(self):
        """Test plugin missing security_level in STANDARD mode."""
        definition = {
            "type": "local_csv",
            "path": "data.csv",
        }

        with pytest.raises(ConfigurationError, match="Plugin 'datasource' validation failed"):
            validate_plugin_definition(definition, "datasource", mode=SecureMode.STANDARD)


class TestSuiteConfigurationValidation:
    """Test suite configuration validation."""

    def test_validate_suite_with_defaults(self):
        """Test suite configuration with suite defaults."""
        suite_config = {
            "suite_defaults": {
                "datasource": {
                    "type": "local_csv",
                    "path": "data.csv",
                    "security_level": "OFFICIAL",
                },
                "llm": {
                    "type": "azure_openai",
                    "endpoint": "https://api.openai.com",
                    "security_level": "OFFICIAL",
                },
            },
            "experiments": [],
        }

        # Should not raise
        validate_suite_configuration(suite_config, mode=SecureMode.STANDARD)

    def test_validate_suite_with_experiments(self):
        """Test suite configuration with experiment overrides."""
        suite_config = {
            "experiments": [
                {
                    "name": "experiment1",
                    "datasource": {
                        "type": "local_csv",
                        "path": "exp1.csv",
                        "security_level": "OFFICIAL",
                    },
                },
                {
                    "name": "experiment2",
                    "llm": {
                        "type": "azure_openai",
                        "endpoint": "https://api2.openai.com",
                        "security_level": "OFFICIAL",
                    },
                },
            ],
        }

        # Should not raise
        validate_suite_configuration(suite_config, mode=SecureMode.STANDARD)

    def test_validate_suite_experiment_missing_security_level(self):
        """Test suite experiment with missing security_level."""
        suite_config = {
            "experiments": [
                {
                    "name": "experiment1",
                    "datasource": {
                        "type": "local_csv",
                        "path": "exp1.csv",
                    },
                }
            ],
        }

        with pytest.raises(ConfigurationError, match="Experiment\\[0\\] datasource validation failed"):
            validate_suite_configuration(suite_config, mode=SecureMode.STANDARD)

    def test_validate_suite_experiment_with_sinks(self):
        """Test suite experiment with sink overrides."""
        suite_config = {
            "experiments": [
                {
                    "name": "experiment1",
                    "sinks": [
                        {
                            "type": "csv",
                            "path": "output.csv",
                            "security_level": "OFFICIAL",
                        }
                    ],
                }
            ],
        }

        # Should not raise
        validate_suite_configuration(suite_config, mode=SecureMode.STANDARD)

    def test_validate_suite_experiment_sink_missing_security_level(self):
        """Test suite experiment sink with missing security_level."""
        suite_config = {
            "experiments": [
                {
                    "name": "experiment1",
                    "sinks": [
                        {
                            "type": "csv",
                            "path": "output.csv",
                        }
                    ],
                }
            ],
        }

        with pytest.raises(ConfigurationError, match="Experiment\\[0\\] Sink\\[0\\] validation failed"):
            validate_suite_configuration(suite_config, mode=SecureMode.STANDARD)


class TestPromptPackValidation:
    """Test prompt pack configuration validation."""

    def test_validate_prompt_pack_with_sinks(self):
        """Test prompt pack with sink definitions."""
        pack_config = {
            "sinks": [
                {
                    "type": "csv",
                    "path": "output.csv",
                    "security_level": "OFFICIAL",
                }
            ],
        }

        # Should not raise
        validate_prompt_pack(pack_config, mode=SecureMode.STANDARD)

    def test_validate_prompt_pack_sink_missing_security_level(self):
        """Test prompt pack sink with missing security_level."""
        pack_config = {
            "sinks": [
                {
                    "type": "csv",
                    "path": "output.csv",
                }
            ],
        }

        with pytest.raises(ConfigurationError, match="Prompt pack Sink\\[0\\] validation failed"):
            validate_prompt_pack(pack_config, mode=SecureMode.STANDARD)

    def test_validate_prompt_pack_with_middleware(self):
        """Test prompt pack with middleware definitions."""
        pack_config = {
            "llm_middlewares": [
                {"type": "prompt_shield", "enabled": True},
                {"type": "audit_logger", "enabled": True},
            ],
        }

        # Should not raise
        validate_prompt_pack(pack_config, mode=SecureMode.STRICT)

    def test_validate_empty_prompt_pack(self):
        """Test empty prompt pack validation."""
        pack_config = {}

        # Should not raise
        validate_prompt_pack(pack_config, mode=SecureMode.STANDARD)
