import urllib.parse as up

import pandas as pd

from elspeth.retrieval.providers import PgVectorQueryClient


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor()

    def close(self):
        self.closed = True


class _PsycopgShim:
    def __init__(self, seen):
        self.seen = seen

    def connect(self, dsn, **kwargs):
        # capture DSN for assertions
        self.seen.append(dsn)
        return _FakeConn()


def test_pgvector_dsn_appends_timeout_for_uri_dsn(monkeypatch):
    seen = []
    client = PgVectorQueryClient(
        dsn="postgresql://user:pass@localhost/mydb?sslmode=require",
        table="t",
        connect_timeout=5,
    )
    # Override psycopg with shim
    client._psycopg = _PsycopgShim(seen)  # type: ignore[attr-defined]

    list(client.query(namespace="ns", query_vector=[0.0], top_k=1, min_score=0.0))

    assert seen, "connect() should have been called"
    dsn = seen[0]
    parsed = up.urlparse(dsn)
    q = dict(up.parse_qsl(parsed.query))
    assert q.get("connect_timeout") == "5"
    # existing params should be preserved too
    assert q.get("sslmode") == "require"


def test_pgvector_dsn_appends_timeout_for_kv_dsn(monkeypatch):
    seen = []
    client = PgVectorQueryClient(
        dsn="host=localhost dbname=mydb user=me",
        table="t",
        connect_timeout=7,
    )
    client._psycopg = _PsycopgShim(seen)  # type: ignore[attr-defined]

    list(client.query(namespace="ns", query_vector=[0.0], top_k=1, min_score=0.0))

    assert seen, "connect() should have been called"
    dsn = seen[0]
    assert "connect_timeout=7" in dsn
    # ensure space-delimited param (kv-style)
    assert " connect_timeout=7" in dsn or dsn.endswith("connect_timeout=7")

