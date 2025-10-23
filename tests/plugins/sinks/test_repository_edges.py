from __future__ import annotations

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
    sink.allow_missing_token()
    headers = sink._headers()  # type: ignore[attr-defined]
    assert "Authorization" not in headers


def test_github_request_error_transient_flag(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    sink.allow_missing_token()  # Required for dry_run=False without token
    resp = _Resp(500, text="server boom")

    def fake_request(method: str, url: str, **kwargs: Any) -> _Resp:
        return resp

    monkeypatch.setattr(sink.session, "request", fake_request, raising=False)
    with pytest.raises(_RepoRequestError) as exc:
        sink._request("GET", "https://api.github.com/repos/o/r/contents/x")  # type: ignore[attr-defined]
    assert exc.value.status == 500
    assert exc.value.transient is True


def test_github_get_existing_sha_handles_404_and_200(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    sink.allow_missing_token()  # Required for dry_run=False without token

    # First call: 404 -> None
    resp_404 = _Resp(404)

    def request_404(method: str, url: str, **kwargs: Any) -> _Resp:
        return resp_404

    monkeypatch.setattr(sink.session, "request", request_404, raising=False)
    assert sink._get_existing_sha("path.txt") is None  # type: ignore[attr-defined]

    # Second call: 200 with sha
    resp_200 = _Resp(200, json_payload={"sha": "abc123"})

    def request_200(method: str, url: str, **kwargs: Any) -> _Resp:
        return resp_200

    monkeypatch.setattr(sink.session, "request", request_200, raising=False)
    assert sink._get_existing_sha("path.txt") == "abc123"  # type: ignore[attr-defined]
