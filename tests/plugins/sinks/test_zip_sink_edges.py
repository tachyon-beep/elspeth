import io
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from elspeth.core.base.protocols import Artifact
from elspeth.plugins.nodes.sinks.zip_bundle import ZipResultSink


def _results_payload() -> dict:
    return {
        "results": [
            {"row": {"A": 1, "B": "=1+1"}, "response": {"content": "ok"}},
            {"row": {"A": 2}, "response": {"content": "ok2"}, "responses": {"alt": {"content": "x"}}},
        ],
        "aggregates": {"score_stats": {"overall": {"mean": 0.5, "std": 0.1}}},
        "cost_summary": {"tokens": 10},
    }


def test_zip_includes_manifest_results_and_csv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    base = tmp_path / "out"
    base.mkdir()
    sink = ZipResultSink(
        base_path=base,
        bundle_name="exp",
        timestamped=False,
        include_manifest=True,
        include_results=True,
        include_csv=True,
        sanitize_formulas=False,  # trigger warning path
        allowed_base_path=base,
    )

    sink.write(_results_payload(), metadata={"experiment": "exp", "security_level": "OFFICIAL", "determinism_level": "low"})
    archive = base / "exp.zip"
    assert archive.exists()

    with ZipFile(archive, "r") as z:
        names = set(z.namelist())
        assert {"results.json", "manifest.json", "results.csv"}.issubset(names)
        # CSV present and contains headers
        csv_data = z.read("results.csv").decode("utf-8")
        assert "llm_content" in csv_data
        # Manifest summarizes rows
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        assert manifest["rows"] == 2

    # Warning when sanitization disabled
    assert any("ZIP sink sanitization disabled" in rec.message for rec in caplog.records)


def test_zip_safe_name_nul_raises_and_skip_on_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    base = tmp_path / "out"
    base.mkdir()
    sink = ZipResultSink(base_path=base, bundle_name="exp", timestamped=False, include_csv=False, on_error="skip", allowed_base_path=base)
    # Prepare additional artifact with NUL in metadata filename to trigger ValueError in _safe_name
    art = Artifact(id="1", type="file/json", payload={"a": 1}, metadata={"filename": "bad\x00name.json"})
    sink.prepare_artifacts({"extra": [art]})
    sink.write(_results_payload(), metadata={"name": "exp"})
    # Creation skipped due to error, file absent
    assert not (base / "exp.zip").exists()
    assert any("ZIP sink failed; skipping archive" in rec.message for rec in caplog.records)


def test_zip_additional_inputs_sanitize_and_write(tmp_path: Path) -> None:
    base = tmp_path / "out"
    base.mkdir()
    sink = ZipResultSink(base_path=base, bundle_name="exp", timestamped=False, include_csv=False, allowed_base_path=base)
    # Artifact with unsafe filename characters to sanitize
    payload = {"extra": True}
    art = Artifact(id="1", type="file/json", payload=payload, metadata={"filename": "unsafe/..name?.json"})
    sink.prepare_artifacts({"attachments": [art]})
    sink.write(_results_payload(), metadata={"name": "exp"})
    archive = base / "exp.zip"
    assert archive.exists()
    with ZipFile(archive, "r") as z:
        names = z.namelist()
        # Special characters replaced; expect name_.json suffix
        assert any(n.endswith("name_.json") for n in names)
