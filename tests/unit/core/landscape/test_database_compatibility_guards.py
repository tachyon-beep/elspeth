"""Regression tests for LandscapeDB schema and journal compatibility guardrails."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text

import elspeth.core.landscape.database as database_module
from elspeth.core.landscape.database import LandscapeDB, SchemaCompatibilityError


def _make_instance(url: str) -> LandscapeDB:
    """Create a LandscapeDB instance without running constructor side effects."""
    instance = LandscapeDB.__new__(LandscapeDB)
    instance.connection_string = url
    instance._passphrase = None
    instance._journal = None
    instance._engine = create_engine(url, echo=False)
    return instance


class TestSchemaCompatibilityGuards:
    """Coverage for fail-fast schema compatibility checks."""

    def test_validate_schema_reports_missing_tables_with_actionable_guidance(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Existing partial Landscape DBs must fail with clear remediation text."""
        db_path = tmp_path / "partial_landscape.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            # "runs" is a known Landscape table, so this DB is recognized as partial.
            conn.execute(text("CREATE TABLE runs (run_id TEXT PRIMARY KEY)"))
        engine.dispose()

        instance = _make_instance(f"sqlite:///{db_path}")
        monkeypatch.setattr(database_module, "_REQUIRED_COLUMNS", [])
        monkeypatch.setattr(database_module, "_REQUIRED_FOREIGN_KEYS", [])

        with pytest.raises(SchemaCompatibilityError) as exc_info:
            instance._validate_schema()

        msg = str(exc_info.value)
        assert "Landscape database schema is outdated." in msg
        assert "Missing tables:" in msg
        assert "To fix this, either:" in msg
        assert "Delete the database file and let ELSPETH recreate it" in msg
        assert "elspeth landscape migrate" in msg
        assert f"Database: sqlite:///{db_path}" in msg
        instance.close()

    def test_validate_schema_reports_missing_required_columns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing required columns must be listed deterministically in the error."""
        db_path = tmp_path / "missing_columns.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE tokens (token_id TEXT PRIMARY KEY)"))
        engine.dispose()

        instance = _make_instance(f"sqlite:///{db_path}")
        monkeypatch.setattr(database_module, "metadata", SimpleNamespace(tables={"tokens": object()}))
        monkeypatch.setattr(database_module, "_REQUIRED_COLUMNS", [("tokens", "expand_group_id")])
        monkeypatch.setattr(database_module, "_REQUIRED_FOREIGN_KEYS", [])

        with pytest.raises(SchemaCompatibilityError) as exc_info:
            instance._validate_schema()

        msg = str(exc_info.value)
        assert "Missing columns: tokens.expand_group_id" in msg
        assert "To fix this, either:" in msg
        instance.close()

    def test_validate_schema_reports_missing_required_foreign_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing required foreign keys must fail fast with table/column context."""
        db_path = tmp_path / "missing_fk.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE transform_errors (token_id TEXT, transform_id TEXT)"))
        engine.dispose()

        instance = _make_instance(f"sqlite:///{db_path}")
        monkeypatch.setattr(database_module, "metadata", SimpleNamespace(tables={"transform_errors": object()}))
        monkeypatch.setattr(database_module, "_REQUIRED_COLUMNS", [])
        monkeypatch.setattr(database_module, "_REQUIRED_FOREIGN_KEYS", [("transform_errors", "token_id", "tokens")])

        with pytest.raises(SchemaCompatibilityError) as exc_info:
            instance._validate_schema()

        msg = str(exc_info.value)
        assert "Missing foreign keys:" in msg
        assert "transform_errors.token_id" in msg
        assert "tokens" in msg
        assert "To fix this, either:" in msg
        instance.close()


class TestJournalPathGuards:
    """Coverage for from_url journal path derivation failure modes."""

    def test_from_url_dump_to_jsonl_requires_explicit_path_for_non_sqlite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-SQLite URLs must provide dump_to_jsonl_path explicitly."""
        mock_create_engine = Mock(return_value=Mock())
        monkeypatch.setattr(database_module, "create_engine", mock_create_engine)

        with pytest.raises(ValueError, match="dump_to_jsonl requires dump_to_jsonl_path for non-SQLite databases"):
            LandscapeDB.from_url("postgresql://user:pass@host/db", dump_to_jsonl=True)

        mock_create_engine.assert_called_once_with("postgresql://user:pass@host/db", echo=False)

    def test_from_url_dump_to_jsonl_rejects_in_memory_sqlite_without_path(self) -> None:
        """In-memory SQLite has no file path, so automatic journal derivation must fail."""
        with pytest.raises(ValueError, match="dump_to_jsonl requires a file-backed SQLite database"):
            LandscapeDB.from_url("sqlite:///:memory:", dump_to_jsonl=True)
