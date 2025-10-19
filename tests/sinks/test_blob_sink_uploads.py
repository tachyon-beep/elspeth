from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path

import pytest

from elspeth.adapters.blob_store import BlobConfig
from elspeth.core.base.protocols import Artifact
from elspeth.plugins.nodes.sinks.blob import BlobResultSink
from elspeth.plugins.nodes.sinks.blob import AzureBlobArtifactsSink, _blob_is_transient_error


def _make_blob_config_file(tmp_path: Path) -> Path:
    cfg = textwrap.dedent(
        """
        default:
          connection_name: test
          azureml_datastore_uri: azureml://subscriptions/xxx/resourcegroups/rg/workspaces/ws/datastores/ds/paths/path
          storage_uri: https://acct.blob.core.windows.net/container/prefix
        """
    ).strip()
    p = tmp_path / "blob.yaml"
    p.write_text(cfg, encoding="utf-8")
    return p


class StubClient:
    def __init__(self):
        self.staged: list[tuple[str, bytes]] = []
        self.committed: list[list[str]] = []
        self.uploads: list[bytes] = []
        self.metadata: list[object] = []
        self._exists = False

    def stage_block(self, block_id: str, data: bytes) -> None:
        self.staged.append((block_id, data))

    def commit_block_list(self, block_ids: list[str], metadata=None, content_settings=None) -> None:  # noqa: D401
        self.committed.append(block_ids)
        self.metadata.append((metadata, content_settings))

    def upload_blob(self, data: bytes, *, overwrite: bool, content_type: str, metadata=None) -> None:  # noqa: D401
        self.uploads.append(data)

    def exists(self) -> bool:
        return self._exists


def test_chunked_upload_and_manifest(tmp_path: Path, monkeypatch):
    cfg_path = _make_blob_config_file(tmp_path)

    # Ensure ContentSettings path executes
    import types

    class CS:
        def __init__(self, **_kwargs):  # noqa: D401
            pass

    monkeypatch.setattr("elspeth.plugins.nodes.sinks.blob.ContentSettings", CS, raising=False)

    sink = BlobResultSink(
        config_path=cfg_path,
        upload_chunk_size=8,
        include_manifest=True,
        overwrite=True,
        path_template="prefix/{date}",
    )

    stub = StubClient()
    monkeypatch.setattr(sink, "_create_blob_client", lambda _name: stub)

    # Results large enough to trigger chunking
    results = {"results": [{"row": {"i": i}} for i in range(5)], "extra": "x" * 64}
    sink.write(results, metadata={"experiment": "e"})

    # At least one chunked commit performed
    assert stub.committed
    # Manifest also uploaded either via commit or single upload
    assert stub.committed or stub.uploads


def test_on_error_skip_on_bad_template(tmp_path: Path, monkeypatch):
    cfg_path = _make_blob_config_file(tmp_path)
    sink = BlobResultSink(
        config_path=cfg_path,
        path_template="bad/{missing}",
        on_error="skip",
        include_manifest=False,
    )
    # Should not raise due to on_error=skip when template formatting fails
    sink.write({"results": []}, metadata={})


def test_overwrite_guard_exists_skip(tmp_path: Path, monkeypatch):
    cfg_path = _make_blob_config_file(tmp_path)
    sink = BlobResultSink(
        config_path=cfg_path,
        overwrite=False,
        on_error="skip",
    )
    stub = StubClient()
    stub._exists = True  # Force exists() True to trigger guard
    monkeypatch.setattr(sink, "_create_blob_client", lambda _name: stub)
    # Small payload to avoid chunking complexity
    sink.write({"results": []}, metadata={})


def test_artifact_bytes_variants():
    # Path payload
    tmp = Path("test_payload.json")
    try:
        tmp.write_text(json.dumps({"a": 1}))
        a1 = Artifact(id="1", type="json", path=str(tmp))
        out = BlobResultSink._artifact_bytes(a1)
        assert out.startswith(b"{")

        # Bytes payload
        a2 = Artifact(id="2", type="bin", payload=b"abc")
        assert BlobResultSink._artifact_bytes(a2) == b"abc"

        # File-like payload
        a3 = Artifact(id="3", type="bin", payload=io.BytesIO(b"xyz"))
        assert BlobResultSink._artifact_bytes(a3) == b"xyz"

        # Invalid payload
        with pytest.raises(ValueError):
            _ = BlobResultSink._artifact_bytes(Artifact(id="4", type="x"))
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


def test_resolve_credential_paths(tmp_path: Path, monkeypatch):
    # Credential provided directly
    cfg_path = _make_blob_config_file(tmp_path)
    sink = BlobResultSink(config_path=cfg_path, credential="TOKEN")
    cfg = sink.config
    assert sink._resolve_credential(cfg) == "TOKEN"

    # credential_env path
    sink2 = BlobResultSink(config_path=cfg_path, credential_env="BLOB_CRED_ENV")
    monkeypatch.setenv("BLOB_CRED_ENV", "ENVVAL")
    assert sink2._resolve_credential(sink2.config) == "ENVVAL"

    # sas_token path
    cfg_yaml = textwrap.dedent(
        """
        default:
          connection_name: test
          azureml_datastore_uri: azureml://sub/rg/ws/datastores/ds/paths/path
          account_name: acct
          container_name: container
          blob_path: prefix
          sas_token: ?abc
        """
    ).strip()
    cfg2_path = tmp_path / "blob2.yaml"
    cfg2_path.write_text(cfg_yaml, encoding="utf-8")
    sink3 = BlobResultSink(config_path=cfg2_path)
    assert sink3._resolve_credential(sink3.config) == "abc"

    # azure-identity fallback path: if installed, returns DefaultAzureCredential; otherwise None
    sink4 = BlobResultSink(config_path=cfg_path)
    res = sink4._resolve_credential(sink4.config)
    assert (res is None) or (res.__class__.__name__.lower().endswith("defaultazurecredential"))


def test_azure_blob_artifacts_sink_write(tmp_path: Path, monkeypatch):
    cfg_path = _make_blob_config_file(tmp_path)
    folder = tmp_path / "artifacts"
    folder.mkdir()
    (folder / "a.txt").write_text("x", encoding="utf-8")

    class Stub:
        def __init__(self):
            self.uploads = []

        def upload_blob(self, data, *, overwrite, content_type, metadata):  # noqa: D401
            self.uploads.append((data, overwrite, content_type, metadata))

    sink = AzureBlobArtifactsSink(config_path=cfg_path, folder_path=str(folder), path_template="pfx")
    stub = Stub()
    monkeypatch.setattr(sink, "_create_blob_client", lambda _name: stub)
    sink.write({"results": []}, metadata={"experiment": "e"})
    assert stub.uploads


def test_blob_transient_error_classifier():
    class E1(Exception):
        status_code = 503

    class Resp:
        def __init__(self, code):
            self.status_code = code

    class E2(Exception):
        def __init__(self):
            self.response = Resp(429)

    class TimeoutBoom(Exception):
        pass

    TimeoutBoom.__name__ = "TimeoutError"

    assert _blob_is_transient_error(E1())
    assert _blob_is_transient_error(E2())
    assert _blob_is_transient_error(TimeoutBoom())
    assert not _blob_is_transient_error(RuntimeError("nope"))
