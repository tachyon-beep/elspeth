"""Tests for ZipResultSink bundles."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from elspeth.core.interfaces import Artifact
from elspeth.plugins.outputs.zip_bundle import ZipResultSink


def _sample_results():
    return {
        "results": [
            {
                "row": {"APPID": "1", "danger": "=42"},
                "response": {"content": "hello"},
            }
        ],
        "aggregates": {"score_stats": {"overall": {"mean": 0.9}}},
        "failures": [{"row": {"APPID": "2"}, "error": "boom"}],
    }


def test_zip_result_sink_creates_archive(tmp_path: Path) -> None:
    sink = ZipResultSink(
        base_path=tmp_path,
        bundle_name="bundle",
        timestamped=False,
        include_manifest=True,
        include_results=True,
        include_csv=True,
    )

    sink.prepare_artifacts(
        {
            "bundle": [
                Artifact(id="prepared", type="text/plain", payload="prepared-text"),
            ]
        }
    )

    sink.write(_sample_results(), metadata={"experiment": "demo", "security_level": "secret"})

    archive_path = tmp_path / "bundle.zip"
    assert archive_path.exists()
    with ZipFile(archive_path) as zf:
        entries = set(zf.namelist())
        assert entries == {"results.json", "manifest.json", "results.csv", "artifact_1"}
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["metadata"]["experiment"] == "demo"
        assert manifest["sanitization"]["enabled"] is True
        csv_content = zf.read("results.csv").decode("utf-8")
        assert "'=42" in csv_content  # sanitized dangerous value

    artifacts = sink.collect_artifacts()
    assert artifacts["zip"].metadata["security_level"] == "secret"
    assert artifacts["zip"].metadata["sanitization"]["guard"] == "'"
    # State cleared after collection.
    assert sink.collect_artifacts() == {}


def test_zip_result_sink_skip_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenZip:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def writestr(self, *args, **kwargs):
            raise RuntimeError("zip failure")

    monkeypatch.setattr("elspeth.plugins.outputs.zip_bundle.ZipFile", BrokenZip)

    sink = ZipResultSink(base_path=tmp_path, bundle_name="fail", timestamped=False, on_error="skip")
    sink.write({"results": []})
    assert not (tmp_path / "fail.zip").exists()
