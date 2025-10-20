from __future__ import annotations

import pytest

from elspeth.plugins.nodes.sinks.repository import AzureDevOpsRepoSink, GitHubRepoSink, _RepoRequestError
from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink
from elspeth.plugins.nodes.sinks.blob import BlobResultSink


def test_azure_devops_ensure_path_leading_slash():
    sink = AzureDevOpsRepoSink(organization="o", project="p", repository="r")
    assert sink._ensure_path("/x") == "/x"  # type: ignore[attr-defined]
    assert sink._ensure_path("x") == "/x"  # type: ignore[attr-defined]


def test_github_request_error_non_transient(monkeypatch):
    sink = GitHubRepoSink(owner="o", repo="r", dry_run=False)
    resp = type("_Resp", (), {"status_code": 404, "text": "not found"})()

    def fake_request(method, url, **kwargs):  # noqa: D401
        return resp

    monkeypatch.setattr(sink.session, "request", fake_request, raising=False)
    with pytest.raises(_RepoRequestError) as exc:
        sink._request("GET", "https://api.github.com/repos/o/r/contents/x")  # type: ignore[attr-defined]
    assert exc.value.status == 404
    assert exc.value.transient is False


def test_strict_mode_strict_branches_exercised(monkeypatch, tmp_path):
    monkeypatch.setenv("ELSPETH_SECURE_MODE", "strict")
    # Repository sink (implementation logs, validation layer enforces in config)
    s1 = GitHubRepoSink(owner="o", repo="r", on_error="skip")
    assert s1.on_error == "skip"
    # Blob sink
    cfg = tmp_path / "b.yaml"
    cfg.write_text(
        """
default:
  connection_name: c
  azureml_datastore_uri: azureml://fake
  storage_uri: https://example.blob.core.windows.net/container/prefix
        """,
        encoding="utf-8",
    )
    s2 = BlobResultSink(config_path=cfg, on_error="skip")
    assert s2.on_error == "skip"
    # Signed sink
    s3 = SignedArtifactSink(base_path=tmp_path, on_error="skip")
    assert s3.on_error == "skip"
