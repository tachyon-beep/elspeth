from __future__ import annotations

from urllib.parse import urlparse, parse_qs

import pytest

from elspeth.retrieval.providers import PgVectorQueryClient


def _client(connect_timeout: int | float | None = 5) -> PgVectorQueryClient:
    # Use a placeholder DSN and table; tests do not call query(), so no DB needed
    return PgVectorQueryClient(dsn="postgresql://user:pass@host/db", table="elspeth_rag", connect_timeout=connect_timeout)


def test_uri_dsn_appends_or_overrides_query_param() -> None:
    cli = _client(connect_timeout=5)
    dsn = "postgresql://user:pass@host:5432/db?sslmode=require"
    out = cli._dsn_with_connect_timeout(dsn)
    parsed = urlparse(out)
    q = parse_qs(parsed.query)
    assert q.get("sslmode") == ["require"]
    assert q.get("connect_timeout") == ["5"]


def test_uri_dsn_overrides_existing_connect_timeout() -> None:
    cli = _client(connect_timeout=7)
    dsn = "postgresql://u:p@h/db?connect_timeout=3&sslmode=disable"
    out = cli._dsn_with_connect_timeout(dsn)
    q = parse_qs(urlparse(out).query)
    assert q.get("connect_timeout") == ["7"]
    assert q.get("sslmode") == ["disable"]


def test_key_value_dsn_append() -> None:
    cli = _client(connect_timeout=11)
    dsn = "host=localhost dbname=mydb"
    out = cli._dsn_with_connect_timeout(dsn)
    assert out.endswith(" connect_timeout=11")


def test_malformed_urlparse_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force urlparse to raise to exercise fallback path
    import elspeth.retrieval.providers as providers

    def _boom(*_args, **_kwargs):  # noqa: D401
        raise ValueError("broken")

    monkeypatch.setattr(providers, "urlparse", _boom)
    cli = _client(connect_timeout=13)
    dsn = "host=myhost dbname=mydb"
    out = cli._dsn_with_connect_timeout(dsn)
    assert out.endswith(" connect_timeout=13")
