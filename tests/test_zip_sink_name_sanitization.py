from __future__ import annotations

import zipfile
from pathlib import Path

from elspeth.core.base.protocols import Artifact
from elspeth.plugins.nodes.sinks.zip_bundle import ZipResultSink


def _results(n: int = 1) -> dict:
    return {"results": [{"row": {"a": i}} for i in range(n)]}


def _artifact_with_name(name: str, data: bytes = b"x") -> Artifact:
    return Artifact(id="a1", type="file/octet-stream", payload=data, metadata={"filename": name})


def test_zip_sink_sanitizes_entry_names(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    sink = ZipResultSink(base_path=base, bundle_name="bundle", timestamped=False, include_results=False, include_manifest=False)
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    # Add artifact with traversal and illegal characters in name
    art = _artifact_with_name("../../evil?name.txt")
    sink.prepare_artifacts({"in": [art]})
    sink.write(_results(), metadata={"experiment": "e"})
    archive = base / "bundle.zip"
    assert archive.exists()
    with zipfile.ZipFile(archive, "r") as zf:
        names = set(zf.namelist())
        # Traversal removed and '?' sanitized to '_'
        assert "evil_name.txt" in names


def test_zip_sink_rejects_nul_byte_names_skip(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    sink = ZipResultSink(
        base_path=base,
        bundle_name="bad",
        timestamped=False,
        include_results=False,
        include_manifest=False,
        on_error="skip",
    )
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    bad = _artifact_with_name("bad\x00name.txt")
    sink.prepare_artifacts({"in": [bad]})
    sink.write(_results(), metadata={"experiment": "e"})
    # On skip, archive should not have been created
    assert not (base / "bad.zip").exists()
