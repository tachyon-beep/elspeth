import json
from pathlib import Path

import pytest

from elspeth.plugins.outputs.local_bundle import LocalBundleSink


def test_local_bundle_sink_creates_bundle(tmp_path, assert_sanitized_artifact):
    base = tmp_path / "archives"
    sink = LocalBundleSink(
        base_path=base,
        bundle_name="exp1",
        timestamped=False,
        write_json=True,
        write_csv=True,
    )

    sink.write(
        {
            "results": [
                {
                    "row": {"APPID": "1", "field": "value"},
                    "response": {"content": "ok"},
                }
            ],
            "aggregates": {"score": {"mean": 0.5}},
        },
        metadata={"experiment": "exp1"},
    )

    bundle_dir = base / "exp1"
    assert bundle_dir.exists()

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    results_json = json.loads((bundle_dir / "results.json").read_text(encoding="utf-8"))
    csv_path = bundle_dir / "results.csv"

    assert manifest["rows"] == 1
    assert manifest["metadata"]["experiment"] == "exp1"
    assert manifest["sanitization"] == {"enabled": True, "guard": "'"}
    assert "field" in manifest["columns"]
    assert results_json["results"][0]["row"]["APPID"] == "1"
    assert csv_path.exists()

    assert_sanitized_artifact(csv_path)


def test_file_copy_sink_happy_path(tmp_path):
    from elspeth.core.interfaces import Artifact
    from elspeth.plugins.outputs.file_copy import FileCopySink

    src = tmp_path / "source.txt"
    src.write_text("payload", encoding="utf-8")
    sink = FileCopySink(destination=str(tmp_path / "dest.txt"))
    sink.prepare_artifacts(
        {
            "input": [
                Artifact(
                    id="a1",
                    type="text/plain",
                    path=str(src),
                    metadata={"content_type": "text/plain"},
                )
            ]
        }
    )
    sink.write({}, metadata={"security_level": "official"})
    artifacts = sink.collect_artifacts()
    copied = Path(artifacts["file"].path)
    assert copied.read_text(encoding="utf-8") == "payload"
    assert artifacts["file"].metadata["content_type"] == "text/plain"
    assert artifacts["file"].security_level == "official"


def test_file_copy_sink_skip_on_missing_artifact(tmp_path, caplog):
    from elspeth.plugins.outputs.file_copy import FileCopySink

    sink = FileCopySink(destination=str(tmp_path / "dest.txt"), on_error="skip")
    sink.prepare_artifacts({})
    with caplog.at_level("WARNING"):
        sink.write({}, metadata={})
    assert not (tmp_path / "dest.txt").exists()
    assert any("requires an input artifact" in record.message for record in caplog.records)


def test_file_copy_sink_skip_when_source_missing(tmp_path, caplog):
    from elspeth.core.interfaces import Artifact
    from elspeth.plugins.outputs.file_copy import FileCopySink

    sink = FileCopySink(destination=str(tmp_path / "dest.txt"), on_error="skip")
    sink.prepare_artifacts(
        {"input": [Artifact(id="a1", type="text/plain", path=str(tmp_path / "missing.txt"))]}
    )
    with caplog.at_level("WARNING"):
        sink.write({}, metadata={})
    assert not (tmp_path / "dest.txt").exists()
    assert any("Source artifact path not found" in record.message for record in caplog.records)


def test_file_copy_sink_overwrite_protection(tmp_path):
    from elspeth.core.interfaces import Artifact
    from elspeth.plugins.outputs.file_copy import FileCopySink

    src = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    src.write_text("payload", encoding="utf-8")
    dest.write_text("existing", encoding="utf-8")

    sink = FileCopySink(destination=str(dest), overwrite=False)
    sink.prepare_artifacts({"input": [Artifact(id="a1", type="text/plain", path=str(src))]})
    with pytest.raises(FileExistsError):
        sink.write({}, metadata={})
