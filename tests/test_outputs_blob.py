import json
from pathlib import Path

import pytest
import yaml

from elspeth.plugins.nodes.sinks.blob import BlobResultSink


def create_blob_config(tmp_path: Path) -> Path:
    cfg = {
        "default": {
            "connection_name": "conn",
            "azureml_datastore_uri": "azureml://fake",
            "storage_uri": "https://example.blob.core.windows.net/container/output",
        }
    }
    path = tmp_path / "blob.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


class DummyBlobClient:
    def __init__(self, name: str, captured: list[dict[str, object]]):
        self.name = name
        self._captured = captured

    def exists(self):  # pragma: no cover - exercised indirectly
        return False

    def upload_blob(self, data, overwrite=True, content_type=None, metadata=None):
        payload = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        try:
            payload = json.loads(payload)
        except Exception:  # pragma: no cover - fallback for binary content
            pass
        self._captured.append(
            {
                "name": self.name,
                "payload": payload,
                "overwrite": overwrite,
                "content_type": content_type,
                "metadata": metadata,
            }
        )


@pytest.mark.parametrize("path_template", [None, "runs/{experiment}/results.json"])
def test_blob_result_sink_uploads(tmp_path, monkeypatch, path_template):
    config_path = create_blob_config(tmp_path)
    captured: list[dict[str, object]] = []

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        path_template=path_template,
        include_manifest=True,
        metadata={"env": "prod", "build": 42},
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_create_blob_client",
        lambda self, name: DummyBlobClient(name, captured),
    )

    sink.write(
        {
            "results": [{"row": {"APPID": "1"}, "response": {"content": "ok"}}],
            "aggregates": {"score": {"mean": 0.8}},
        },
        metadata={"experiment": "exp1", "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    )

    assert len(captured) == 2
    payload_entry = next(item for item in captured if item["name"].endswith("results.json"))
    manifest_entry = next(item for item in captured if str(item["name"]).endswith("manifest.json"))

    assert payload_entry["payload"]["results"][0]["row"]["APPID"] == "1"
    assert payload_entry["content_type"] == "application/json"
    assert payload_entry["metadata"] == {"env": "prod", "build": "42", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}
    manifest = manifest_entry["payload"]
    assert manifest["rows"] == 1
    assert manifest["metadata"]["experiment"] == "exp1"
    assert manifest["metadata"]["security_level"] == "OFFICIAL"
    assert manifest["metadata"]["determinism_level"] == "guaranteed"
    assert manifest["aggregates"]["score"]["mean"] == 0.8


def test_blob_result_sink_chunked_upload(tmp_path, monkeypatch):
    config_path = create_blob_config(tmp_path)
    staged = []
    committed = {}

    class ChunkClient:
        def __init__(self, name):
            self.name = name

        def stage_block(self, block_id, data):
            staged.append((block_id, bytes(data)))

        def commit_block_list(self, block_ids, metadata=None, content_settings=None):
            committed["ids"] = block_ids
            committed["metadata"] = metadata
            committed["settings"] = content_settings

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        include_manifest=False,
        upload_chunk_size=4,
        metadata={"tag": "blue", "build": 7},
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_create_blob_client",
        lambda self, name: ChunkClient(name),
    )

    sink.write(
        {"results": [{"row": {"APPID": "1"}, "response": {"content": "x" * 20}}]},
        metadata={"security_level": "SECRET", "determinism_level": "guaranteed"},
    )

    assert len(staged) > 1
    assert committed["ids"] == sorted(committed["ids"])
    assert committed["metadata"] == {"tag": "blue", "build": "7", "security_level": "SECRET", "determinism_level": "guaranteed"}
    settings = committed.get("settings")
    if settings is not None:
        assert getattr(settings, "content_type", None) == "application/json"


def test_blob_result_sink_prepared_artifacts(tmp_path, monkeypatch):
    from elspeth.core.base.protocols import Artifact

    artifact_path = tmp_path / "artifact.bin"
    artifact_path.write_bytes(b"payload-bytes")

    config_path = create_blob_config(tmp_path)
    uploads = []

    class RecordingClient:
        def __init__(self, name):
            self.name = name

        def upload_blob(self, data, overwrite=True, content_type=None, metadata=None):
            uploads.append(
                {
                    "name": self.name,
                    "data": data if isinstance(data, bytes) else data.encode("utf-8"),
                    "overwrite": overwrite,
                    "content_type": content_type,
                    "metadata": metadata,
                }
            )

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        include_manifest=False,
    )

    sink.prepare_artifacts(
        {
            "bundle": [
                Artifact(
                    id="a1",
                    type="blob",
                    payload={"hello": "world"},
                    metadata={"content_type": "application/vnd.custom+json"},
                ),
                Artifact(
                    id="a2",
                    type="blob",
                    path=str(artifact_path),
                    security_level="SECRET",
                ),
            ]
        }
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_create_blob_client",
        lambda self, name: RecordingClient(name),
    )

    sink.write({}, metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    assert len(uploads) == 2
    first, second = uploads
    assert first["name"].endswith("results.json")
    assert json.loads(first["data"].decode("utf-8")) == {"hello": "world"}
    assert first["content_type"] == "application/vnd.custom+json"
    assert second["name"].split("/")[-1].startswith("results_2")
    assert second["data"] == b"payload-bytes"
    assert second["metadata"] == {"security_level": "SECRET", "determinism_level": "guaranteed"}


def test_blob_result_sink_manifest_template(tmp_path, monkeypatch):
    config_path = create_blob_config(tmp_path)
    writes = []

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        path_template="runs/{experiment}/",
        manifest_template="manifests/{experiment}/",
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_upload_bytes",
        lambda self, name, data, *, content_type, upload_metadata: writes.append((name, content_type, upload_metadata, data)),
    )

    sink.write(
        {"results": [{"row": {"APPID": "1"}, "response": {"content": "ok"}}]},
        metadata={"experiment": "exp1"},
    )

    paths = [entry[0] for entry in writes]
    assert "runs/exp1/results.json" in paths
    manifest_path = next(path for path in paths if path.startswith("manifests"))
    assert manifest_path.endswith("results.json.manifest.json")
    manifest_entry = next(item for item in writes if item[0] == manifest_path)
    assert json.loads(manifest_entry[3].decode("utf-8"))["metadata"]["experiment"] == "exp1"


def test_blob_result_sink_skip_on_upload_error(tmp_path, monkeypatch, caplog):
    config_path = create_blob_config(tmp_path)
    sink = BlobResultSink(config_path=config_path, profile="default", on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(BlobResultSink, "_upload_bytes", boom)

    with caplog.at_level("WARNING"):
        sink.write({"results": []}, metadata={"experiment": "exp1"})

    assert any("Blob sink failed" in record.message for record in caplog.records)


def test_blob_result_sink_abort_on_upload_error(tmp_path, monkeypatch):
    config_path = create_blob_config(tmp_path)
    sink = BlobResultSink(config_path=config_path, profile="default", on_error="abort")
    def _raise_runtimeerror(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("boom")
    monkeypatch.setattr(BlobResultSink, "_upload_bytes", _raise_runtimeerror)
    with pytest.raises(RuntimeError):
        sink.write({"results": []}, metadata={})


def test_blob_result_sink_missing_placeholder_raises(tmp_path):
    config_path = create_blob_config(tmp_path)
    sink = BlobResultSink(config_path=config_path, profile="default", path_template="runs/{missing}/")
    with pytest.raises(ValueError):
        sink.write({"results": []}, metadata={"experiment": "exp1"})


def test_blob_result_sink_stage_block_failure_skip(tmp_path, monkeypatch, caplog):
    config_path = create_blob_config(tmp_path)

    class FailingStageClient:
        def __init__(self, name):
            self.name = name

        def stage_block(self, block_id, chunk):
            raise RuntimeError("stage failure")

        def commit_block_list(self, block_ids, metadata=None, content_settings=None):
            raise AssertionError("commit should not be called")

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        upload_chunk_size=4,
        on_error="skip",
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_create_blob_client",
        lambda self, name: FailingStageClient(name),
    )

    payload = {"results": [{"row": {"APPID": "1"}, "response": {"content": "x" * 12}}]}
    with caplog.at_level("WARNING"):
        sink.write(payload, metadata={"experiment": "exp1"})

    assert any("Blob sink failed" in record.message for record in caplog.records)


def test_blob_result_sink_stage_block_failure_abort(tmp_path, monkeypatch):
    config_path = create_blob_config(tmp_path)

    class FailingStageClient:
        def stage_block(self, block_id, chunk):
            raise RuntimeError("stage failure")

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        upload_chunk_size=2,
        on_error="abort",
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_create_blob_client",
        lambda self, name: FailingStageClient(),
    )

    with pytest.raises(RuntimeError):
        sink.write({"results": [{"row": {}, "response": {"content": "abcdef"}}]}, metadata={})


def test_blob_result_sink_commit_failure(tmp_path, monkeypatch, caplog):
    config_path = create_blob_config(tmp_path)
    staged = []

    class CommitFailClient:
        def stage_block(self, block_id, chunk):
            staged.append(block_id)

        def commit_block_list(self, block_ids, metadata=None, content_settings=None):
            raise RuntimeError("commit failure")

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        upload_chunk_size=3,
        on_error="skip",
    )

    monkeypatch.setattr(
        BlobResultSink,
        "_create_blob_client",
        lambda self, name: CommitFailClient(),
    )

    with caplog.at_level("WARNING"):
        sink.write({"results": [{"row": {}, "response": {"content": "abcdef"}}]}, metadata={})

    assert staged, "stage_block should have been called"
    assert any("Blob sink failed" in record.message for record in caplog.records)


def test_blob_result_sink_uses_content_settings(tmp_path, monkeypatch):
    config_path = create_blob_config(tmp_path)
    committed = {}

    class ChunkClient:
        def __init__(self):
            self.blocks = []

        def stage_block(self, block_id, chunk):
            self.blocks.append(block_id)

        def commit_block_list(self, block_ids, metadata=None, content_settings=None):
            committed["block_ids"] = block_ids
            committed["content_settings"] = content_settings

    class DummyContentSettings:
        def __init__(self, content_type):
            self.content_type = content_type

    sink = BlobResultSink(
        config_path=config_path,
        profile="default",
        upload_chunk_size=4,
    )

    monkeypatch.setattr(BlobResultSink, "_create_blob_client", lambda self, name: ChunkClient())
    monkeypatch.setattr("elspeth.plugins.nodes.sinks.blob.ContentSettings", DummyContentSettings)

    sink.write({"results": [{"row": {}, "response": {"content": "abcd" * 4}}]}, metadata={})

    assert isinstance(committed["content_settings"], DummyContentSettings)
    assert committed["content_settings"].content_type == "application/json"
