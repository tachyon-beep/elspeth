from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import pytest

from elspeth.plugins.nodes.sinks.repository import (
    GitHubRepoSink,
    PreparedFile,
    _default_context,
)


def test_default_context_derives_fields():
    ts = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    ctx = _default_context({"name": "exp"}, ts)
    assert ctx["experiment"] == "exp"
    assert ctx["timestamp"].startswith("20250102T030405Z")
    assert ctx["date"] == "2025-01-02"
    assert ctx["time"] == "030405"


def test_resolve_prefix_missing_placeholder_raises():
    sink = GitHubRepoSink(owner="o", repo="r")
    # Use a template that references a missing key
    sink.path_template = "experiments/{experiment}/{missing}"
    with pytest.raises(ValueError):
        sink._resolve_prefix({"experiment": "e"})  # type: ignore[arg-type]


def test_github_upload_base64_and_sha(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r")

    calls: list[tuple[str, str, dict[str, Any]]] = []

    def _fake_request(method: str, url: str, **kwargs: Any):  # noqa: D401
        calls.append((method, url, kwargs))
        class R:
            status_code = 201
            def json(self):  # noqa: D401
                return {}
        return R()

    # First file should include sha; second should not
    monkeypatch.setattr(sink, "_request", _fake_request)
    monkeypatch.setattr(sink, "_get_existing_sha", lambda path: "deadbeef" if path.endswith("one.json") else None)

    files = [
        PreparedFile(path="p/one.json", content=b"{}"),
        PreparedFile(path="p/two.bin", content=b"\x00\x01"),
    ]
    sink._upload(files, commit_message="msg", metadata={}, context={}, timestamp=datetime.now(timezone.utc))  # type: ignore[arg-type]

    # Two PUT calls made
    assert len(calls) == 2
    m1, url1, kw1 = calls[0]
    m2, url2, kw2 = calls[1]
    assert m1 == m2 == "PUT"
    assert url1.endswith("/contents/p/one.json")
    assert url2.endswith("/contents/p/two.bin")

    # Payloads contain base64 content
    c1 = kw1["json"]["content"]
    c2 = kw2["json"]["content"]
    assert base64.b64decode(c1) == b"{}"
    assert base64.b64decode(c2) == b"\x00\x01"
    # First includes sha, second does not
    assert kw1["json"].get("sha") == "deadbeef"
    assert "sha" not in kw2["json"]

