import json
from pathlib import Path

import pytest
import yaml

from dmp.plugins.outputs.blob import BlobResultSink


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
        metadata={"experiment": "exp1", "security_level": "official"},
    )

    assert len(captured) == 2
    payload_entry = next(item for item in captured if item["name"].endswith("results.json"))
    manifest_entry = next(item for item in captured if str(item["name"]).endswith("manifest.json"))

    assert payload_entry["payload"]["results"][0]["row"]["APPID"] == "1"
    assert payload_entry["content_type"] == "application/json"
    assert payload_entry["metadata"] == {"env": "prod", "build": "42", "security_level": "official"}
    manifest = manifest_entry["payload"]
    assert manifest["rows"] == 1
    assert manifest["metadata"]["experiment"] == "exp1"
    assert manifest["metadata"]["security_level"] == "official"
    assert manifest["aggregates"]["score"]["mean"] == 0.8
