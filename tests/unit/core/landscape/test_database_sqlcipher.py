# tests/unit/core/landscape/test_database_sqlcipher.py
"""Tests for SQLCipher encryption-at-rest support in LandscapeDB.

All tests skip if sqlcipher3 is not installed (optional 'security' extra).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

sqlcipher3 = pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed (install with: uv pip install 'elspeth[security]')")


class TestSQLCipherCreateAndRead:
    """Basic CRUD operations on an encrypted database."""

    def test_sqlcipher_create_and_read(self, tmp_path: Path) -> None:
        from sqlalchemy import select

        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.schema import runs_table

        db_path = tmp_path / "encrypted.db"
        passphrase = "test-passphrase-42"

        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=passphrase)
        try:
            # Insert a run record with all NOT NULL columns
            with db.connection() as conn:
                conn.execute(
                    runs_table.insert().values(
                        run_id="test-run-001",
                        status="RUNNING",
                        started_at=datetime.now(UTC),
                        config_hash="abc123",
                        settings_json="{}",
                        canonical_version="1.0.0",
                    )
                )

            # Read it back
            with db.connection() as conn:
                result = conn.execute(select(runs_table).where(runs_table.c.run_id == "test-run-001")).fetchone()
                assert result is not None
                assert result.run_id == "test-run-001"
                assert result.status == "RUNNING"
        finally:
            db.close()


class TestSQLCipherPragmaOrdering:
    """PRAGMA key must execute before WAL/FK/busy_timeout."""

    def test_sqlcipher_pragma_key_first(self, tmp_path: Path) -> None:
        """Verify that PRAGMA key runs before other PRAGMAs by checking
        that WAL mode is active (which requires a valid connection)."""
        from elspeth.core.landscape.database import LandscapeDB

        db_path = tmp_path / "pragma_order.db"
        passphrase = "pragma-test"

        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=passphrase)
        try:
            # If PRAGMA key wasn't first, the WAL/FK PRAGMAs would have
            # failed and this query would fail too
            with db.connection() as conn:
                from sqlalchemy import text

                result = conn.execute(text("PRAGMA journal_mode")).fetchone()
                assert result is not None
                assert result[0] == "wal"
        finally:
            db.close()


class TestSQLCipherWrongPassphrase:
    """Wrong passphrase produces a clear error."""

    def test_sqlcipher_wrong_passphrase(self, tmp_path: Path) -> None:
        from elspeth.core.landscape.database import LandscapeDB, SchemaCompatibilityError

        db_path = tmp_path / "wrong_pass.db"

        # Create with one passphrase
        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase="correct-passphrase")
        db.close()

        # Open with wrong passphrase — should fail with clear message
        with pytest.raises((SchemaCompatibilityError, Exception)) as exc_info:
            LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase="wrong-passphrase")
        # Verify the error is actionable (either our custom message or SQLCipher's)
        error_msg = str(exc_info.value).lower()
        assert "file is not a database" in error_msg or "encrypted" in error_msg or "passphrase" in error_msg


class TestSQLCipherNoPassphraseOnEncrypted:
    """Plain SQLite against an encrypted DB fails clearly."""

    def test_sqlcipher_no_passphrase_on_encrypted(self, tmp_path: Path) -> None:
        from elspeth.core.landscape.database import LandscapeDB, SchemaCompatibilityError

        db_path = tmp_path / "encrypted_no_pass.db"

        # Create encrypted DB
        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase="secret-key")
        db.close()

        # Try opening without passphrase (plain SQLite) — should fail
        # Standard sqlite3 sees garbage when reading SQLCipher-encrypted files
        with pytest.raises((SchemaCompatibilityError, Exception)) as exc_info:
            LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=None)
        error_msg = str(exc_info.value).lower()
        assert "file is not a database" in error_msg or "encrypted" in error_msg or "passphrase" in error_msg


class TestSQLCipherSchemaIntegrity:
    """All tables, indexes, and constraints are created in encrypted DB."""

    def test_sqlcipher_schema_integrity(self, tmp_path: Path) -> None:
        from sqlalchemy import inspect

        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.schema import metadata

        db_path = tmp_path / "schema_check.db"
        passphrase = "schema-test"

        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=passphrase)
        try:
            inspector = inspect(db.engine)
            actual_tables = set(inspector.get_table_names())
            expected_tables = set(metadata.tables.keys())

            assert expected_tables == actual_tables, f"Missing: {expected_tables - actual_tables}, Extra: {actual_tables - expected_tables}"

            # Verify a composite FK exists (nodes table FK integrity)
            fks = inspector.get_foreign_keys("node_states")
            fk_tables = {fk["referred_table"] for fk in fks}
            assert "nodes" in fk_tables, "node_states should reference nodes table"
        finally:
            db.close()


class TestSQLCipherWALMode:
    """WAL journal mode is active on SQLCipher connections."""

    def test_sqlcipher_wal_mode_active(self, tmp_path: Path) -> None:
        from elspeth.core.landscape.database import LandscapeDB

        db_path = tmp_path / "wal_test.db"
        passphrase = "wal-test"

        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=passphrase)
        try:
            with db.connection() as conn:
                from sqlalchemy import text

                result = conn.execute(text("PRAGMA journal_mode")).fetchone()
                assert result is not None
                assert result[0] == "wal"
        finally:
            db.close()


class TestSQLCipherForeignKeys:
    """FK violations are rejected on encrypted connections."""

    def test_sqlcipher_foreign_keys_enforced(self, tmp_path: Path) -> None:
        from sqlalchemy import text

        from elspeth.core.landscape.database import LandscapeDB

        db_path = tmp_path / "fk_test.db"
        passphrase = "fk-test"

        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=passphrase)
        try:
            # Insert a node with non-existent run_id — FK should reject.
            # Note: sqlcipher3.dbapi2.IntegrityError may not be wrapped by
            # sqlalchemy.exc.IntegrityError when using the creator pattern,
            # so we catch both via Exception and verify the message.
            with pytest.raises(Exception, match="FOREIGN KEY constraint failed"), db.connection() as conn:
                conn.execute(
                    text(
                        "INSERT INTO nodes (node_id, run_id, plugin_name, node_type, "
                        "plugin_version, determinism, config_hash, config_json, "
                        "sequence_in_pipeline, registered_at) "
                        "VALUES (:nid, :rid, :pn, :nt, :pv, :det, :ch, :cj, :seq, :rat)"
                    ),
                    {
                        "nid": "node-001",
                        "rid": "nonexistent-run",
                        "pn": "csv",
                        "nt": "source",
                        "pv": "1.0.0",
                        "det": "deterministic",
                        "ch": "hash",
                        "cj": "{}",
                        "seq": 0,
                        "rat": datetime.now(UTC).isoformat(),
                    },
                )
        finally:
            db.close()


class TestPlainSQLiteUnchanged:
    """passphrase=None still produces an unencrypted, standard-sqlite3-readable DB."""

    def test_plain_sqlite_unchanged(self, tmp_path: Path) -> None:
        import sqlite3

        from elspeth.core.landscape.database import LandscapeDB

        db_path = tmp_path / "plain.db"

        db = LandscapeDB.from_url(f"sqlite:///{db_path}", passphrase=None)
        db.close()

        # Standard sqlite3 should be able to open and read it
        conn = sqlite3.connect(str(db_path))
        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = {row[0] for row in tables}
            assert "runs" in table_names
            assert "nodes" in table_names
        finally:
            conn.close()


class TestSQLCipherRejectsMemory:
    """SQLCipher with :memory: raises a clear ValueError."""

    def test_sqlcipher_rejects_memory(self) -> None:
        from elspeth.core.landscape.database import LandscapeDB

        with pytest.raises(ValueError, match="file-backed database"):
            LandscapeDB.from_url("sqlite:///:memory:", passphrase="test-key")
