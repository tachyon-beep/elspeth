from __future__ import annotations

import importlib
import sys
import types

import pytest


def test_pgvector_raises_when_sql_module_missing(monkeypatch):
    """Ensure PgVectorQueryClient refuses to run without psycopg.sql.

    We stub a minimal psycopg module without the 'sql' submodule so that
    providers fall back to the guarded branch that raises RuntimeError.
    """

    # Minimal psycopg stub with connect() and a fake connection
    psycopg = types.ModuleType("psycopg")

    class _Cursor:
        def __enter__(self):  # pragma: no cover - trivial
            return self

        def __exit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
            return False

        def execute(self, query, params):  # pragma: no cover - should not be reached
            pass

        def fetchall(self):  # pragma: no cover - should not be reached
            return []

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    def _connect(dsn, autocommit=True):
        return _Conn()

    psycopg.connect = _connect  # type: ignore[attr-defined]

    # Install stub; ensure no psycopg.sql module is present
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    sys.modules.pop("psycopg.sql", None)

    # Import providers fresh so it uses the stubbed psycopg
    sys.modules.pop("elspeth.retrieval.providers", None)
    providers = importlib.import_module("elspeth.retrieval.providers")

    client = providers.PgVectorQueryClient(dsn="postgresql://example", table="t")
    with pytest.raises(RuntimeError, match="psycopg\.sql unavailable|refusing to execute raw SQL fallback|psycopg unavailable"):
        list(client.query("ns", [0.1, 0.2], top_k=1, min_score=0.0))
