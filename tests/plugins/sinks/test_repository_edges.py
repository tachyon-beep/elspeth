from __future__ import annotations

import base64
from typing import Any

import pytest

from elspeth.plugins.nodes.sinks.repository import GitHubRepoSink, _RepoRequestError


class _Resp:
    def __init__(self, status_code: int, text: str = "", json_payload: Any | None = None):
        self.status_code = status_code
        self.text = text
        self._json = json_payload

    def json(self) -> Any:
        return self._json


class _FakeSession:
    def __init__(self, status_code: int = 500, json_payload: Any | None = None, text: str = "err") -> None:
        self.status_code = status_code
        self.json_payload = json_payload
        self.text = text
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:  # noqa: D401
        self.requests.append((method, url, kwargs))
        return _Resp(self.status_code, self.text, self.json_payload)


def test_github_headers_missing_token_raises_in_non_dry_run(monkeypatch):
    # Ensure env token is not set
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    # Use real requests.Session by default; expect missing token to raise
    with pytest.raises(RuntimeError):
        sink._headers()  # type: ignore[attr-defined]


def test_github_headers_without_requests_session_allows_no_auth(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    sink.session = object()  # not a requests.Session, bypasses hard fail
    headers = sink._headers()  # type: ignore[attr-defined]
    assert "Authorization" not in headers


def test_github_request_error_transient_flag(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    sink.session = _FakeSession(status_code=500, text="server boom")
    with pytest.raises(_RepoRequestError) as exc:
        sink._request("GET", "https://api.github.com/repos/o/r/contents/x")  # type: ignore[attr-defined]
    assert exc.value.status == 500
    assert exc.value.transient is True


def test_github_get_existing_sha_handles_404_and_200(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    # First call: 404 -> None
    sink.session = _FakeSession(status_code=404)
    assert sink._get_existing_sha("path.txt") is None  # type: ignore[attr-defined]

    # Second call: 200 with sha
    sink.session = _FakeSession(status_code=200, json_payload={"sha": "abc123"})
    assert sink._get_existing_sha("path.txt") == "abc123"  # type: ignore[attr-defined]

