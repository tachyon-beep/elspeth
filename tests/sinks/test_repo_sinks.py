from __future__ import annotations

import os
from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.repository import (
    AzureDevOpsArtifactsRepoSink,
    AzureDevOpsRepoSink,
    GitHubRepoSink,
    _RepoRequestError,
)
from elspeth.core.security.secure_mode import SecureMode


class DummyResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):  # noqa: D401
        return self._json


class DummySession:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_kwargs):  # noqa: D401
        self.calls.append((method, url))
        return DummyResponse(200, json_data={})


def test_repo_sink_strict_mode_on_error_skip_guard(monkeypatch):
    # Security note: STRICT mode enforces fail-closed policy and rejects
    # on_error='skip' for repository sinks to prevent silent error suppression.
    import elspeth.plugins.nodes.sinks.repository as repo_mod

    monkeypatch.setattr(repo_mod, "get_secure_mode", lambda: SecureMode.STRICT)
    # In STRICT mode, __post_init__ raises ValueError for on_error='skip'
    with pytest.raises(ValueError, match="cannot use on_error='skip' in STRICT mode"):
        GitHubRepoSink(owner="o", repo="r", on_error="skip")


def test_github_dry_run_payload_and_headers(monkeypatch, tmp_path):
    # Dry-run path should append payload and not call network
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=True, session=DummySession())
    sink.write({"results": []}, metadata={"experiment": "e"})
    assert sink._last_payloads and sink._last_payloads[0]["dry_run"] is True

    # Headers without token and real requests.Session raises; with fake session it should not
    # Call _headers directly to exercise missing-token path with real Session
    sink_live = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    # Ensure token not set
    env = "GITHUB_TOKEN"
    if os.getenv(env):
        del os.environ[env]
    with pytest.raises(RuntimeError):
        _ = sink_live._headers()

    # With token: header includes Authorization and caching works
    os.environ[env] = "abc"
    headers1 = sink._headers()
    os.environ[env] = "def"
    headers2 = sink._headers()
    assert headers1 == headers2 and "Authorization" in headers2


def test_github_request_and_existing_sha(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False, session=DummySession())
    os.environ[sink.token_env] = "tok"

    # 404 path returns None
    def _req404(_m, _u, **_k):
        return DummyResponse(404, json_data={})

    monkeypatch.setattr(sink, "_request", _req404)
    assert sink._get_existing_sha("p") is None

    # 200 path returns sha
    def _req200(_m, _u, **_k):
        return DummyResponse(200, json_data={"sha": "abc"})

    monkeypatch.setattr(sink, "_request", _req200)
    assert sink._get_existing_sha("p") == "abc"


def test_github_transient_and_nontransient_skip(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False, on_error="skip", session=DummySession())
    os.environ[sink.token_env] = "tok"

    # Transient error -> skip
    def _boom(*_a, **_k):
        raise _RepoRequestError("x", status=503, transient=True)

    monkeypatch.setattr(sink, "_upload", _boom)
    sink.write({"results": []}, metadata={"experiment": "e"})

    # Non-transient -> still skip due to generic on_error branch
    def _boom2(*_a, **_k):
        raise _RepoRequestError("x", status=400, transient=False)

    monkeypatch.setattr(sink, "_upload", _boom2)
    sink.write({"results": []}, metadata={"experiment": "e"})


def test_ado_helpers_and_artifacts_dry_run(monkeypatch, tmp_path):
    session = DummySession()
    sink = AzureDevOpsRepoSink(
        organization="org",
        project="proj",
        repository="repo",
        session=session,
        dry_run=True,
    )
    # _ensure_path
    assert sink._ensure_path("/a") == "/a"
    assert sink._ensure_path("a") == "/a"

    # Artifacts sink
    folder = tmp_path / "artifacts"
    folder.mkdir()
    (folder / "f.txt").write_text("hello", encoding="utf-8")
    af = AzureDevOpsArtifactsRepoSink(
        organization="org",
        project="proj",
        repository="repo",
        folder_path=str(folder),
        session=session,
        dry_run=True,
    )

    # Stub _get_branch_ref and _item_exists
    monkeypatch.setattr(af, "_get_branch_ref", lambda: "deadbeef")
    monkeypatch.setattr(af, "_item_exists", lambda _p: False)
    # Should not raise and should not perform POST due to dry_run
    af.write({"results": []}, metadata={"experiment": "e"})
