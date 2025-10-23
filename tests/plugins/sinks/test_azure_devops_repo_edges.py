from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from elspeth.plugins.nodes.sinks.repository import AzureDevOpsArtifactsRepoSink, AzureDevOpsRepoSink


class _Resp:
    def __init__(self, status_code: int, text: str = "", json_payload: Any | None = None):
        self.status_code = status_code
        self.text = text
        self._json = json_payload

    def json(self) -> Any:
        return self._json


def test_azure_headers_build_with_token(monkeypatch):
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "t0ken")
    sink = AzureDevOpsRepoSink(
        organization="o",
        project="p",
        repository="r",
        dry_run=False,
    )
    headers = sink._headers()  # type: ignore[attr-defined]
    assert headers["Authorization"].startswith("Basic ")
    # Validate prefix encoding of ":<token>"
    encoded = headers["Authorization"].split()[1]
    assert base64.b64decode(encoded).decode("ascii").startswith(":t0ken")


def test_azure_headers_missing_token_raises(monkeypatch):
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    sink = AzureDevOpsRepoSink(
        organization="o",
        project="p",
        repository="r",
        dry_run=False,
    )
    # Real requests.Session type check matters; use default
    with pytest.raises(RuntimeError):
        sink._headers()  # type: ignore[attr-defined]


def test_azure_get_branch_ref_handles_not_found(monkeypatch):
    # value = [] triggers branch not found
    sink = AzureDevOpsRepoSink(organization="o", project="p", repository="r")
    resp = _Resp(200, json_payload={"value": []})

    def fake_request(method: str, url: str, **kwargs: Any) -> _Resp:
        return resp

    monkeypatch.setattr(sink.session, "request", fake_request, raising=False)
    with pytest.raises(RuntimeError):
        sink._get_branch_ref()  # type: ignore[attr-defined]


def test_azure_item_exists_true_false(monkeypatch):
    sink = AzureDevOpsRepoSink(organization="o", project="p", repository="r")
    # 200 => exists
    resp_true = _Resp(200, json_payload={})

    def request_true(method: str, url: str, **kwargs: Any) -> _Resp:
        return resp_true

    monkeypatch.setattr(sink.session, "request", request_true, raising=False)
    assert sink._item_exists("/x") is True  # type: ignore[attr-defined]
    # 404 => not exists
    sink = AzureDevOpsRepoSink(organization="o", project="p", repository="r")
    resp_false = _Resp(404, json_payload={})

    def request_false(method: str, url: str, **kwargs: Any) -> _Resp:
        return resp_false

    monkeypatch.setattr(sink.session, "request", request_false, raising=False)
    assert sink._item_exists("/x") is False  # type: ignore[attr-defined]


def test_artifacts_collect_changes_add_and_edit(tmp_path: Path, monkeypatch):
    root = tmp_path / "bundle"
    (root / "a").mkdir(parents=True)
    f1 = root / "a" / "one.txt"
    f2 = root / "two.bin"
    f1.write_text("hello", encoding="utf-8")
    f2.write_bytes(b"\x00\x01\x02")

    class S(AzureDevOpsArtifactsRepoSink):
        def __init__(self, **kw):  # noqa: D401
            super().__init__(folder_path=str(root), organization="o", project="p", repository="r")

    sink = S()
    # Force deterministic edit/add mix
    idx = {"/artifacts/a/one.txt": True, "/artifacts/two.bin": False}
    monkeypatch.setattr(sink, "_resolve_prefix", lambda ctx: "artifacts")
    monkeypatch.setattr(sink, "_item_exists", lambda path: idx.get(path, False))
    changes = sink._collect_changes("artifacts")  # type: ignore[attr-defined]
    kinds = {c["changeType"] for c in changes}
    assert kinds == {"add", "edit"}
    # Ensure base64encoded content used for binaries
    for c in changes:
        assert c["newContent"]["contentType"] == "base64encoded"
