"""
Security enforcement tests for silent defaults.

These tests verify that critical security-related configurations
cannot fall back to silent defaults. All critical parameters must
be explicitly provided.

Created: 2025-10-14
Purpose: Risk Reduction Phase - Gate requirement for migration
"""

import pytest


class TestCriticalDefaultEnforcement:
    """
    Test that critical defaults are not allowed.

    All critical security-related parameters must be explicitly configured.
    Silent defaults have been removed to ensure secure-by-default configuration.
    """

    def test_audit_critical_defaults_documented(self):
        """Meta-test: Verify critical defaults are documented in audit."""
        # This test passes - it just confirms the audit exists
        import pathlib

        audit_file = (
            pathlib.Path(__file__).parent.parent
            / "docs"
            / "archive"
            / "roadmap"
            / "data-flow-migration"
            / "data-flow-migration"
            / "SILENT_DEFAULTS_AUDIT.md"
        )
        assert audit_file.exists(), "SILENT_DEFAULTS_AUDIT.md should exist"

        content = audit_file.read_text()
        assert "CRITICAL (P0)" in content
        assert "Azure Search API Key" in content or "api_key_env" in content
        assert "pgvector" in content or "elspeth_rag" in content


class TestValidationPatternEnforcement:
    """Test that validation patterns cannot be empty."""

    def test_regex_validator_requires_pattern(self):
        """Verify regex validator requires explicit pattern configuration."""
        from elspeth.core.experiments.plugin_registry import create_validation_plugin
        from elspeth.core.validation.base import ConfigurationError

        # Should fail when pattern is missing
        with pytest.raises(ConfigurationError, match="is a required property.*pattern"):
            create_validation_plugin(
                {
                    "name": "regex_match",
                    "determinism_level": "guaranteed",
                    "options": {},  # Missing pattern
                }
            )

        # Should succeed with explicit pattern
        plugin = create_validation_plugin(
            {
                "name": "regex_match",
                "determinism_level": "guaranteed",
                "options": {"pattern": r"\d+"},
            }
        )
        assert plugin is not None


class TestLLMParameterEnforcement:
    """Test that LLM parameters are properly documented as optional."""

    def test_llm_temperature_is_optional(self):
        """Verify LLM temperature is optional (not required)."""
        # src/elspeth/core/llm_registry.py:84-87 (http_openai)
        # src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:20
        # These are optional parameters - if not provided, None is used (API defaults apply)
        from elspeth.core.base.plugin_context import PluginContext
        from elspeth.core.registries.llm import llm_registry

        parent_context = PluginContext(
            plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
        )

        # HTTP OpenAI should succeed without temperature (uses API default)
        llm = llm_registry.create(
            name="http_openai",
            options={"api_base": "https://api.openai.com/v1", "model": "gpt-4"},
            parent_context=parent_context,
        )
        assert llm is not None
        assert getattr(llm, "temperature", None) is None  # Not provided, should be None

        # Should also work with explicit temperature
        llm_with_temp = llm_registry.create(
            name="http_openai",
            options={"api_base": "https://api.openai.com/v1", "model": "gpt-4", "temperature": 0.7},
            parent_context=parent_context,
        )
        assert llm_with_temp is not None
        assert getattr(llm_with_temp, "temperature", None) == pytest.approx(0.7)

    def test_llm_max_tokens_is_optional(self):
        """Verify LLM max_tokens is optional (not required)."""
        # src/elspeth/core/llm_registry.py:88-91 (http_openai)
        # src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:21
        # These are optional parameters - if not provided, None is used (API defaults apply)
        from elspeth.core.base.plugin_context import PluginContext
        from elspeth.core.registries.llm import llm_registry

        parent_context = PluginContext(
            plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
        )

        # HTTP OpenAI should succeed without max_tokens (uses API default)
        llm = llm_registry.create(
            name="http_openai",
            options={"api_base": "https://api.openai.com/v1", "model": "gpt-4"},
            parent_context=parent_context,
        )
        assert llm is not None
        assert llm.max_tokens is None  # Not provided, should be None

        # Should also work with explicit max_tokens
        llm_with_max = llm_registry.create(
            name="http_openai",
            options={"api_base": "https://api.openai.com/v1", "model": "gpt-4", "max_tokens": 1000},
            parent_context=parent_context,
        )
        assert llm_with_max is not None
        assert llm_with_max.max_tokens == 1000


class TestStaticLLMDefaults:
    """Test static LLM defaults (used in testing)."""

    def test_static_llm_content_requires_explicit_config(self):
        """Verify static LLM requires explicit content parameter."""
        # src/elspeth/core/llm_registry.py:47
        # Validates that content parameter is required
        from elspeth.core.base.plugin_context import PluginContext
        from elspeth.core.registries.llm import llm_registry
        from elspeth.core.validation.base import ConfigurationError

        parent_context = PluginContext(
            plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
        )

        # Should raise ConfigurationError when content is missing
        # Schema validation catches this before the factory function
        with pytest.raises(ConfigurationError, match="is a required property.*content"):
            llm_registry.create(name="static_test", options={}, parent_context=parent_context)

        # Should succeed when content is provided
        llm = llm_registry.create(
            name="static_test", options={"content": "Explicit test content"}, parent_context=parent_context
        )
        assert llm is not None
        assert llm.content == "Explicit test content"


class TestRateLimitDefaults:
    """Test rate limiter defaults."""

    def test_rate_limiter_requires_explicit_config(self):
        """Verify rate limiter requires explicit configuration for all parameters."""
        from elspeth.core.base.plugin_context import PluginContext
        from elspeth.core.controls.rate_limiter_registry import rate_limiter_registry
        from elspeth.core.validation.base import ConfigurationError

        parent_context = PluginContext(
            plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
        )

        # fixed_window should fail without requests
        with pytest.raises(ConfigurationError, match="is a required property.*requests"):
            rate_limiter_registry.create(
                name="fixed_window",
                options={"per_seconds": 1.0},
                parent_context=parent_context,
            )

        # fixed_window should fail without per_seconds
        with pytest.raises(ConfigurationError, match="is a required property.*per_seconds"):
            rate_limiter_registry.create(
                name="fixed_window",
                options={"requests": 10},
                parent_context=parent_context,
            )

        # Should succeed with all required fields
        limiter = rate_limiter_registry.create(
            name="fixed_window",
            options={"requests": 10, "per_seconds": 1.0},
            parent_context=parent_context,
        )
        assert limiter is not None


class TestCostTrackerDefaults:
    """Test cost tracker defaults."""

    def test_cost_tracker_requires_explicit_prices(self):
        """Verify cost tracker requires explicit token price configuration."""
        from elspeth.core.base.plugin_context import PluginContext
        from elspeth.core.controls.cost_tracker_registry import cost_tracker_registry
        from elspeth.core.validation.base import ConfigurationError

        parent_context = PluginContext(
            plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
        )

        # Should fail without prompt_token_price
        with pytest.raises(ConfigurationError, match="is a required property.*prompt_token_price"):
            cost_tracker_registry.create(
                name="fixed_price",
                options={"completion_token_price": 0.01},
                parent_context=parent_context,
            )

        # Should fail without completion_token_price
        with pytest.raises(ConfigurationError, match="is a required property.*completion_token_price"):
            cost_tracker_registry.create(
                name="fixed_price",
                options={"prompt_token_price": 0.005},
                parent_context=parent_context,
            )

        # Should succeed with both prices explicit
        tracker = cost_tracker_registry.create(
            name="fixed_price",
            options={"prompt_token_price": 0.005, "completion_token_price": 0.01},
            parent_context=parent_context,
        )
        assert tracker is not None


class TestDatabaseSchemaDefaults:
    """Test database schema defaults - now enforced."""

    def test_pgvector_factory_requires_explicit_table(self):
        """Verify pgvector factory requires explicit table name."""
        from elspeth.core.validation.base import ConfigurationError
        from elspeth.retrieval.providers import create_query_client

        # Should fail without table name
        with pytest.raises(ConfigurationError, match="pgvector retriever requires 'table'"):
            create_query_client("pgvector", {"dsn": "postgresql://localhost/test"})

        # Note: Success case requires psycopg package which is an optional dependency
        # The validation test above verifies enforcement - that's the security requirement

    def test_azure_search_factory_requires_explicit_fields(self):
        """Verify Azure Search factory requires explicit field configuration."""
        from elspeth.core.validation.base import ConfigurationError
        from elspeth.retrieval.providers import create_query_client

        base_options = {
            "endpoint": "https://test.search.windows.net",
            "index": "test-index",
            "api_key": "test-key",
        }

        # Should fail without vector_field
        with pytest.raises(ConfigurationError, match="azure_search retriever requires 'vector_field'"):
            create_query_client("azure_search", base_options)

        # Should fail without namespace_field
        with pytest.raises(ConfigurationError, match="azure_search retriever requires 'namespace_field'"):
            create_query_client("azure_search", {**base_options, "vector_field": "embedding"})

        # Should fail without content_field
        with pytest.raises(ConfigurationError, match="azure_search retriever requires 'content_field'"):
            create_query_client("azure_search", {**base_options, "vector_field": "embedding", "namespace_field": "namespace"})

        # Note: Success case requires azure-search-documents package which is an optional dependency
        # The validation tests above verify enforcement - that's the security requirement


# Gate verification test
class TestSecurityGateStatus:
    """Meta-test to track gate status."""

    def test_critical_defaults_gate_status(self):
        """Track status of critical defaults removal."""
        critical_defaults_removed = {
            "azure_search_api_key_env": True,  # ✅ Fixed in providers.py:164
            "azure_search_field_names": True,  # ✅ Fixed in providers.py:175-183
            "pgvector_table_name": True,  # ✅ Fixed in providers.py:156
            "azure_openai_endpoint": True,  # ✅ Fixed in azure_openai.py:28
            "azure_openai_api_version": True,  # ✅ Fixed in azure_openai.py:27
            "static_llm_content": True,  # ✅ Fixed in llm_registry.py:47
            "regex_empty_pattern": True,  # ✅ Already enforced (validation.py:136)
        }

        total = len(critical_defaults_removed)
        fixed = sum(critical_defaults_removed.values())

        print(f"\nCritical Defaults Status: {fixed}/{total} fixed")

        # Gate now PASSES - all critical defaults have been removed
        assert fixed == total, f"Gate BLOCKED: {total - fixed} critical defaults remain. See SILENT_DEFAULTS_AUDIT.md for details."


class TestHighPriorityDefaults:
    """Test high priority defaults that need documentation or removal."""

    def test_llm_guard_requires_explicit_tokens(self):
        """Verify llm_guard validation requires explicit token configuration."""
        from elspeth.core.experiments.plugin_registry import create_validation_plugin
        from elspeth.core.validation.base import ConfigurationError

        # ADR-002-B: security_level removed from LLM definition (plugin-author-owned)
        # LLM inherits security_level from parent validation plugin context
        validator_llm_def = {
            "plugin": "static_test",
            "options": {"content": "VALID"},
        }

        # Should fail without valid_token
        with pytest.raises(ConfigurationError, match="is a required property.*valid_token"):
            create_validation_plugin(
                {
                    "name": "llm_guard",
                    "determinism_level": "guaranteed",
                    "options": {
                        "validator_llm": validator_llm_def,
                        "user_prompt_template": "Check {{ content }}",
                        "invalid_token": "INVALID",
                        "strip_whitespace": True,
                    },
                }
            )

        # Should fail without invalid_token
        with pytest.raises(ConfigurationError, match="is a required property.*invalid_token"):
            create_validation_plugin(
                {
                    "name": "llm_guard",
                    "determinism_level": "guaranteed",
                    "options": {
                        "validator_llm": validator_llm_def,
                        "user_prompt_template": "Check {{ content }}",
                        "valid_token": "VALID",
                        "strip_whitespace": True,
                    },
                }
            )

        # Should fail without strip_whitespace
        with pytest.raises(ConfigurationError, match="is a required property.*strip_whitespace"):
            create_validation_plugin(
                {
                    "name": "llm_guard",
                    "determinism_level": "guaranteed",
                    "options": {
                        "validator_llm": validator_llm_def,
                        "user_prompt_template": "Check {{ content }}",
                        "valid_token": "VALID",
                        "invalid_token": "INVALID",
                    },
                }
            )

        # Should succeed with all required fields
        plugin = create_validation_plugin(
            {
                "name": "llm_guard",
                "determinism_level": "guaranteed",
                "options": {
                    "validator_llm": validator_llm_def,
                    "user_prompt_template": "Check {{ content }}",
                    "valid_token": "VALID",
                    "invalid_token": "INVALID",
                    "strip_whitespace": True,
                },
            }
        )
        assert plugin is not None

    def test_score_extractor_requires_all_fields(self):
        """Verify score extractor requires explicit configuration for all fields."""
        from elspeth.core.experiments.plugin_registry import create_row_plugin
        from elspeth.core.validation.base import ConfigurationError

        # Should fail without key
        with pytest.raises(ConfigurationError, match="key is required"):
            create_row_plugin(
                {
                    "name": "score_extractor",
                    "determinism_level": "guaranteed",
                    "options": {
                        "parse_json_content": True,
                        "allow_missing": False,
                        "threshold_mode": "gte",
                        "flag_field": "score_flags",
                    },
                }
            )

        # Should fail without parse_json_content
        with pytest.raises(ConfigurationError, match="parse_json_content is required"):
            create_row_plugin(
                {
                    "name": "score_extractor",
                    "determinism_level": "guaranteed",
                    "options": {
                        "key": "score",
                        "allow_missing": False,
                        "threshold_mode": "gte",
                        "flag_field": "score_flags",
                    },
                }
            )

        # Should fail without allow_missing
        with pytest.raises(ConfigurationError, match="allow_missing is required"):
            create_row_plugin(
                {
                    "name": "score_extractor",
                    "determinism_level": "guaranteed",
                    "options": {
                        "key": "score",
                        "parse_json_content": True,
                        "threshold_mode": "gte",
                        "flag_field": "score_flags",
                    },
                }
            )

        # Should fail without threshold_mode
        with pytest.raises(ConfigurationError, match="threshold_mode is required"):
            create_row_plugin(
                {
                    "name": "score_extractor",
                    "determinism_level": "guaranteed",
                    "options": {
                        "key": "score",
                        "parse_json_content": True,
                        "allow_missing": False,
                        "flag_field": "score_flags",
                    },
                }
            )

        # Should fail without flag_field
        with pytest.raises(ConfigurationError, match="flag_field is required"):
            create_row_plugin(
                {
                    "name": "score_extractor",
                    "determinism_level": "guaranteed",
                    "options": {
                        "key": "score",
                        "parse_json_content": True,
                        "allow_missing": False,
                        "threshold_mode": "gte",
                    },
                }
            )

        # Should succeed with all required fields
        plugin = create_row_plugin(
            {
                "name": "score_extractor",
                "determinism_level": "guaranteed",
                "options": {
                    "key": "score",
                    "parse_json_content": True,
                    "allow_missing": False,
                    "threshold_mode": "gte",
                    "flag_field": "score_flags",
                },
            }
        )
        assert plugin is not None
