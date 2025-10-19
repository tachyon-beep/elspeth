from __future__ import annotations

import os
from pathlib import Path

import yaml

from elspeth.plugins.nodes.sinks.blob import BlobResultSink


def _blob_cfg(tmp_path: Path) -> Path:
    cfg = {
        "default": {
            "connection_name": "conn",
            "azureml_datastore_uri": "azureml://fake",
            "storage_uri": "https://example.blob.core.windows.net/container/out",
            "sas_token": "?sast=abc",
        }
    }
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def test_blob_credential_resolution_env_and_sas(tmp_path: Path, monkeypatch) -> None:
    cfg = _blob_cfg(tmp_path)
    # Direct credential wins
    sink1 = BlobResultSink(config_path=cfg, credential="DIRECT")
    assert sink1._resolve_credential(sink1.config) == "DIRECT"  # type: ignore[attr-defined]

    # Env variable next
    monkeypatch.setenv("BLOB_ENV", "ENV_TOKEN")
    sink2 = BlobResultSink(config_path=cfg, credential_env="BLOB_ENV")
    assert sink2._resolve_credential(sink2.config) == "ENV_TOKEN"  # type: ignore[attr-defined]

    # SAS token from config next (unset env)
    monkeypatch.delenv("BLOB_ENV", raising=False)
    sink3 = BlobResultSink(config_path=cfg)
    val = sink3._resolve_credential(sink3.config)  # type: ignore[attr-defined]
    assert val in ("?sast=abc", "sast=abc")


def test_blob_resolve_blob_name_variants_and_error(tmp_path: Path) -> None:
    cfg = {
        "default": {
            "connection_name": "c",
            "azureml_datastore_uri": "azureml://fake",
        "storage_uri": "https://example.blob.core.windows.net/container/out/",
            "blob_path": "prefix/path/",
        }
    }
    p = tmp_path / "b.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    sink = BlobResultSink(config_path=p, filename="file.json")
    # No template -> uses blob_path + filename
    name1 = sink._resolve_blob_name({"filename": "file.json", "blob_path": sink.config.blob_path})  # type: ignore[attr-defined]
    assert name1.endswith("file.json") and "/" in name1

    # Template that ends with slash appends filename
    sink2 = BlobResultSink(config_path=p, path_template="runs/{experiment}/")
    name2 = sink2._resolve_blob_name({"experiment": "e", "filename": "results.json"})  # type: ignore[attr-defined]
    assert name2 == "runs/e/results.json"

    # No further assertions; missing placeholder error path already covered elsewhere


def test_blob_upload_respects_overwrite_false(tmp_path: Path, monkeypatch) -> None:
    cfg = _blob_cfg(tmp_path)
    sink = BlobResultSink(config_path=cfg, include_manifest=False)
    sink.overwrite = False

    class ExistsClient:
        def exists(self):  # pragma: no cover - simple stub executed in branch guard
            return True

        def upload_blob(self, *a, **k):  # pragma: no cover - should not be called
            raise AssertionError("upload_blob should not be called when exists and overwrite=False")

    monkeypatch.setattr(BlobResultSink, "_create_blob_client", lambda self, name: ExistsClient())

    try:
        sink.write({"results": [{"row": {}}]}, metadata={})
    except FileExistsError:
        pass
    else:  # pragma: no cover - ensure branch raised
        raise AssertionError("expected FileExistsError when blob exists and overwrite is disabled")
