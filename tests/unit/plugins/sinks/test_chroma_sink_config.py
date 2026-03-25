"""Tests for ChromaSink configuration validation."""

from __future__ import annotations

import pytest

from elspeth.plugins.infrastructure.config_base import PluginConfigError
from elspeth.plugins.sinks.chroma_sink import ChromaSinkConfig


class TestFieldMappingConfig:
    """Tests for field_mapping validation rules."""

    def test_valid_config(self) -> None:
        config = ChromaSinkConfig.from_dict(
            {
                "collection": "science-facts",
                "mode": "persistent",
                "persist_directory": "./chroma_data",
                "distance_function": "cosine",
                "field_mapping": {
                    "document": "text_content",
                    "id": "doc_id",
                    "metadata": ["topic", "subtopic"],
                },
                "on_duplicate": "overwrite",
                "schema": {
                    "mode": "fixed",
                    "fields": [
                        "doc_id: str",
                        "text_content: str",
                        "topic: str",
                        "subtopic: str",
                    ],
                },
            }
        )
        assert config.collection == "science-facts"
        assert config.field_mapping.document == "text_content"
        assert config.field_mapping.id == "doc_id"
        assert config.field_mapping.metadata == ["topic", "subtopic"]

    def test_field_mapping_required(self) -> None:
        with pytest.raises(Exception, match="field_mapping"):
            ChromaSinkConfig.from_dict(
                {
                    "collection": "test",
                    "mode": "persistent",
                    "persist_directory": "./data",
                    "schema": {"mode": "fixed", "fields": ["id: str", "text: str"]},
                }
            )

    def test_on_duplicate_default_is_overwrite(self) -> None:
        config = ChromaSinkConfig.from_dict(
            {
                "collection": "test",
                "mode": "persistent",
                "persist_directory": "./data",
                "field_mapping": {"document": "text", "id": "id", "metadata": []},
                "schema": {"mode": "fixed", "fields": ["id: str", "text: str"]},
            }
        )
        assert config.on_duplicate == "overwrite"

    def test_on_duplicate_rejects_invalid_value(self) -> None:
        with pytest.raises(PluginConfigError, match="on_duplicate"):
            ChromaSinkConfig.from_dict(
                {
                    "collection": "test",
                    "mode": "persistent",
                    "persist_directory": "./data",
                    "field_mapping": {
                        "document": "text",
                        "id": "id",
                        "metadata": [],
                    },
                    "on_duplicate": "invalid",
                    "schema": {"mode": "fixed", "fields": ["id: str", "text: str"]},
                }
            )

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(Exception, match="extra"):
            ChromaSinkConfig.from_dict(
                {
                    "collection": "test",
                    "mode": "persistent",
                    "persist_directory": "./data",
                    "field_mapping": {
                        "document": "text",
                        "id": "id",
                        "metadata": [],
                    },
                    "unknown_extra": "value",
                    "schema": {"mode": "fixed", "fields": ["id: str", "text: str"]},
                }
            )


class TestConnectionValidation:
    """Tests that ChromaConnectionConfig validation flows through."""

    def test_persistent_mode_requires_persist_directory(self) -> None:
        with pytest.raises(Exception, match="persist_directory"):
            ChromaSinkConfig.from_dict(
                {
                    "collection": "test",
                    "mode": "persistent",
                    "field_mapping": {"document": "t", "id": "i", "metadata": []},
                    "schema": {"mode": "fixed", "fields": ["i: str", "t: str"]},
                }
            )

    def test_client_mode_requires_host(self) -> None:
        with pytest.raises(Exception, match="host"):
            ChromaSinkConfig.from_dict(
                {
                    "collection": "test",
                    "mode": "client",
                    "field_mapping": {"document": "t", "id": "i", "metadata": []},
                    "schema": {"mode": "fixed", "fields": ["i: str", "t: str"]},
                }
            )
