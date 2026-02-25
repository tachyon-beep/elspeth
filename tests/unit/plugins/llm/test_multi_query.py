"""Tests for multi-query LLM support.

Tests for QuerySpec, resolve_queries, OutputFieldConfig, ResponseFormat,
and multi-query transform instantiation via unified LLMTransform.
"""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.plugins.config_base import PluginConfigError
from elspeth.plugins.llm.transform import LLMTransform

# Re-export chaosllm_server fixture for field collision tests
from tests.fixtures.chaosllm import chaosllm_server  # noqa: F401

# ---------------------------------------------------------------------------
# Config helpers (inline, using the new unified format)
# ---------------------------------------------------------------------------

DYNAMIC_SCHEMA = {"mode": "observed"}


def _make_llm_config(**overrides: Any) -> dict[str, Any]:
    """Create valid LLMTransform multi-query config with optional overrides."""
    config: dict[str, Any] = {
        "provider": "azure",
        "deployment_name": "gpt-4o",
        "endpoint": "https://test.openai.azure.com",
        "api_key": "test-key",
        "template": "Evaluate: {{ row.text_content }}",
        "system_prompt": "You are an assessment AI. Respond in JSON.",
        "schema": DYNAMIC_SCHEMA,
        "required_input_fields": [],
        "pool_size": 1,
        "queries": {
            "cs1_diag": {
                "input_fields": {"text_content": "cs1_bg"},
                "output_fields": [
                    {"suffix": "score", "type": "integer"},
                    {"suffix": "rationale", "type": "string"},
                ],
            },
        },
    }
    config.update(overrides)
    return config


class TestOutputFieldConfig:
    """Tests for OutputFieldConfig and JSON schema generation."""

    def test_string_type_to_json_schema(self) -> None:
        """String type generates correct JSON schema."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        config = OutputFieldConfig.from_dict({"suffix": "rationale", "type": "string"})
        schema = config.to_json_schema()

        assert schema == {"type": "string"}

    def test_integer_type_to_json_schema(self) -> None:
        """Integer type generates correct JSON schema."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        config = OutputFieldConfig.from_dict({"suffix": "score", "type": "integer"})
        schema = config.to_json_schema()

        assert schema == {"type": "integer"}

    def test_number_type_to_json_schema(self) -> None:
        """Number type generates correct JSON schema."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        config = OutputFieldConfig.from_dict({"suffix": "probability", "type": "number"})
        schema = config.to_json_schema()

        assert schema == {"type": "number"}

    def test_boolean_type_to_json_schema(self) -> None:
        """Boolean type generates correct JSON schema."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        config = OutputFieldConfig.from_dict({"suffix": "is_valid", "type": "boolean"})
        schema = config.to_json_schema()

        assert schema == {"type": "boolean"}

    def test_enum_type_to_json_schema(self) -> None:
        """Enum type generates JSON schema with allowed values."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        config = OutputFieldConfig.from_dict(
            {
                "suffix": "confidence",
                "type": "enum",
                "values": ["low", "medium", "high"],
            }
        )
        schema = config.to_json_schema()

        assert schema == {"type": "string", "enum": ["low", "medium", "high"]}

    def test_enum_requires_values(self) -> None:
        """Enum type without values raises validation error."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        with pytest.raises(PluginConfigError):
            OutputFieldConfig.from_dict({"suffix": "level", "type": "enum"})

    def test_enum_requires_non_empty_values(self) -> None:
        """Enum type with empty values list raises validation error."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        with pytest.raises(PluginConfigError):
            OutputFieldConfig.from_dict({"suffix": "level", "type": "enum", "values": []})

    def test_non_enum_rejects_values(self) -> None:
        """Non-enum types reject values parameter."""
        from elspeth.plugins.llm.multi_query import OutputFieldConfig

        with pytest.raises(PluginConfigError):
            OutputFieldConfig.from_dict(
                {
                    "suffix": "score",
                    "type": "integer",
                    "values": ["a", "b"],  # Invalid for non-enum
                }
            )


class TestMultiQueryDeclaredOutputFields:
    """Tests for declared_output_fields on unified LLMTransform.

    Field collision detection is enforced centrally by TransformExecutor
    (see TestTransformExecutor in test_executors.py). These tests verify
    that LLMTransform correctly declares its output fields so the
    executor can perform pre-execution collision checks.
    """

    def test_declared_output_fields_contains_response_field(self) -> None:
        """declared_output_fields includes the base response field."""
        transform = LLMTransform(_make_llm_config())
        # LLMTransform declares output fields based on response_field
        assert "llm_response" in transform.declared_output_fields

    def test_declared_output_fields_contains_audit_fields(self) -> None:
        """declared_output_fields includes per-spec audit fields.

        Before centralization, the multi-query collision check only inspected
        output_mapping fields but not audit fields (usage, model, template_hash, etc.).
        declared_output_fields must include these to prevent silent overwrite.
        """
        transform = LLMTransform(_make_llm_config())

        # Guaranteed metadata fields
        assert "llm_response_usage" in transform.declared_output_fields
        assert "llm_response_model" in transform.declared_output_fields
        # Audit fields
        assert "llm_response_template_hash" in transform.declared_output_fields

    def test_declared_output_fields_with_multiple_queries(self) -> None:
        """declared_output_fields covers the base response_field for all configs."""
        config = _make_llm_config(
            queries={
                "cs1_diagnosis": {
                    "input_fields": {"text_content": "cs1_bg"},
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
                        {"suffix": "rationale", "type": "string"},
                    ],
                },
                "cs2_diagnosis": {
                    "input_fields": {"text_content": "cs2_bg"},
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
                        {"suffix": "rationale", "type": "string"},
                    ],
                },
            },
        )

        transform = LLMTransform(config)

        # The unified LLMTransform declares output fields based on response_field,
        # not per-query prefixes. The per-query field construction happens at runtime.
        assert "llm_response" in transform.declared_output_fields
        assert "llm_response_usage" in transform.declared_output_fields

    def test_declared_output_fields_is_nonempty(self) -> None:
        """declared_output_fields is populated for schema evolution recording."""
        transform = LLMTransform(_make_llm_config())
        assert transform.declared_output_fields
