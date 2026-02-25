# tests/unit/plugins/llm/test_plugin_registration.py
"""Tests for unified LLM plugin registration and validation dispatch (Task 10).

Verifies that:
- "llm" plugin dispatches to provider-specific config models
- Old plugin names raise helpful migration errors
- Discovery finds the new LLMTransform plugin
"""

from __future__ import annotations

import pytest

from elspeth.plugins.validation import PluginConfigValidator


class TestLLMPluginConfigDispatch:
    """Tests for _get_transform_config_model provider dispatch."""

    def test_llm_plugin_dispatches_to_azure_config(self) -> None:
        """verify _get_transform_config_model("llm", {"provider": "azure"}) returns AzureOpenAIConfig."""
        from elspeth.plugins.llm.providers.azure import AzureOpenAIConfig

        validator = PluginConfigValidator()
        config_model = validator._get_transform_config_model("llm", {"provider": "azure"})
        assert config_model is AzureOpenAIConfig

    def test_llm_plugin_dispatches_to_openrouter_config(self) -> None:
        """verify _get_transform_config_model("llm", {"provider": "openrouter"}) returns OpenRouterConfig."""
        from elspeth.plugins.llm.providers.openrouter import OpenRouterConfig

        validator = PluginConfigValidator()
        config_model = validator._get_transform_config_model("llm", {"provider": "openrouter"})
        assert config_model is OpenRouterConfig

    def test_llm_plugin_missing_provider_falls_back_to_base(self) -> None:
        """verify missing provider key returns LLMConfig (Pydantic catches the Literal validation)."""
        from elspeth.plugins.llm.base import LLMConfig

        validator = PluginConfigValidator()
        config_model = validator._get_transform_config_model("llm", {})
        assert config_model is LLMConfig

    def test_llm_plugin_unknown_provider_raises(self) -> None:
        """verify unknown provider raises ValueError with valid providers listed."""
        validator = PluginConfigValidator()
        with pytest.raises(ValueError, match="Unknown LLM provider 'fake'"):
            validator._get_transform_config_model("llm", {"provider": "fake"})

    def test_llm_plugin_none_config_falls_back_to_base(self) -> None:
        """verify None config falls back to LLMConfig."""
        from elspeth.plugins.llm.base import LLMConfig

        validator = PluginConfigValidator()
        config_model = validator._get_transform_config_model("llm", None)
        assert config_model is LLMConfig


class TestOldPluginNameMigration:
    """Tests for helpful error messages when using old plugin names."""

    @pytest.mark.parametrize(
        "old_name,expected_provider",
        [
            ("azure_llm", "azure"),
            ("openrouter_llm", "openrouter"),
            ("azure_multi_query_llm", "azure"),
            ("openrouter_multi_query_llm", "openrouter"),
        ],
    )
    def test_old_plugin_names_raise_helpful_error(
        self,
        old_name: str,
        expected_provider: str,
    ) -> None:
        """verify old plugin names raise ValueError with migration guidance."""
        validator = PluginConfigValidator()
        with pytest.raises(ValueError, match=f"replaced by 'llm'.*provider: {expected_provider}"):
            validator._get_transform_config_model(old_name)


class TestBatchPluginsUnchanged:
    """Verify batch plugin entries are unaffected."""

    def test_azure_batch_llm_still_resolves(self) -> None:
        from elspeth.plugins.llm.azure_batch import AzureBatchConfig

        validator = PluginConfigValidator()
        config_model = validator._get_transform_config_model("azure_batch_llm")
        assert config_model is AzureBatchConfig

    def test_openrouter_batch_llm_still_resolves(self) -> None:
        from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchConfig

        validator = PluginConfigValidator()
        config_model = validator._get_transform_config_model("openrouter_batch_llm")
        assert config_model is OpenRouterBatchConfig


class TestLLMPluginDiscovery:
    """Verify the unified LLMTransform is discovered correctly."""

    def test_llm_plugin_discovered_with_correct_name(self) -> None:
        from elspeth.plugins.discovery import discover_all_plugins

        discovered = discover_all_plugins()
        transform_names = [cls.name for cls in discovered["transforms"]]  # type: ignore[attr-defined]
        assert "llm" in transform_names

    def test_llm_plugin_is_non_deterministic(self) -> None:
        from elspeth.contracts import Determinism
        from elspeth.plugins.llm.transform import LLMTransform

        assert LLMTransform.determinism == Determinism.NON_DETERMINISTIC
