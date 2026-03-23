# tests/plugins/config/test_tabular_source_config.py
"""Tests for TabularSourceDataConfig validation."""

import pytest

from elspeth.plugins.infrastructure.config_base import PluginConfigError


class TestTabularSourceDataConfigValidation:
    """Tests for field normalization config option validation."""

    def test_columns_with_python_keyword_raises(self) -> None:
        """columns entry that is Python keyword raises error."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        with pytest.raises(PluginConfigError, match="Python keyword"):
            TabularSourceDataConfig.from_dict(
                {
                    "path": "/tmp/test.csv",
                    "schema": {"mode": "observed"},
                    "on_validation_failure": "quarantine",
                    "columns": ["id", "class", "name"],
                }
            )

    def test_columns_with_invalid_identifier_raises(self) -> None:
        """columns entry that is invalid identifier raises error."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        with pytest.raises(PluginConfigError, match=r"valid.*identifier"):
            TabularSourceDataConfig.from_dict(
                {
                    "path": "/tmp/test.csv",
                    "schema": {"mode": "observed"},
                    "on_validation_failure": "quarantine",
                    "columns": ["id", "123_bad", "name"],
                }
            )

    def test_columns_with_duplicates_raises(self) -> None:
        """columns with duplicate entries raises error."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        with pytest.raises(PluginConfigError, match=r"[Dd]uplicate"):
            TabularSourceDataConfig.from_dict(
                {
                    "path": "/tmp/test.csv",
                    "schema": {"mode": "observed"},
                    "on_validation_failure": "quarantine",
                    "columns": ["id", "name", "id"],
                }
            )

    def test_field_mapping_value_is_keyword_raises(self) -> None:
        """field_mapping value that is Python keyword raises error."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        with pytest.raises(PluginConfigError, match="Python keyword"):
            TabularSourceDataConfig.from_dict(
                {
                    "path": "/tmp/test.csv",
                    "schema": {"mode": "observed"},
                    "on_validation_failure": "quarantine",
                    "field_mapping": {"user_id": "class"},
                }
            )

    def test_valid_config_default(self) -> None:
        """Valid config with defaults passes — field_mapping and columns are None."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict(
            {
                "path": "/tmp/test.csv",
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
            }
        )
        assert cfg.field_mapping is None
        assert cfg.columns is None

    def test_valid_config_with_columns(self) -> None:
        """Valid config with columns passes."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict(
            {
                "path": "/tmp/test.csv",
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "columns": ["id", "name", "amount"],
            }
        )
        assert cfg.columns == ["id", "name", "amount"]

    def test_valid_config_with_mapping(self) -> None:
        """Valid config with field_mapping passes."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict(
            {
                "path": "/tmp/test.csv",
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "field_mapping": {"user_id": "uid"},
            }
        )
        assert cfg.field_mapping == {"user_id": "uid"}

    def test_empty_field_mapping_treated_as_none(self) -> None:
        """Empty field_mapping dict should behave same as None."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict(
            {
                "path": "/tmp/test.csv",
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "field_mapping": {},
            }
        )
        # Empty dict should be allowed (treated as no mapping)
        assert cfg.field_mapping == {}

    def test_single_column_headerless_mode(self) -> None:
        """Columns with single entry should work."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict(
            {
                "path": "/tmp/test.csv",
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "columns": ["id"],
            }
        )
        assert cfg.columns == ["id"]

    def test_normalize_fields_config_key_rejected(self) -> None:
        """normalize_fields is no longer a valid config key — Pydantic rejects unknown fields."""
        from elspeth.plugins.infrastructure.config_base import TabularSourceDataConfig

        with pytest.raises(PluginConfigError):
            TabularSourceDataConfig.from_dict(
                {
                    "path": "/tmp/test.csv",
                    "schema": {"mode": "observed"},
                    "on_validation_failure": "quarantine",
                    "normalize_fields": True,
                }
            )
