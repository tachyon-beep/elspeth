from __future__ import annotations

import os
from pathlib import Path

import pytest

from elspeth.core.base.protocols import Artifact
from elspeth.plugins.nodes.sinks.file_copy import FileCopySink


def _make_artifact(path: Path) -> Artifact:
    return Artifact(id="src", type="file/text", path=str(path), persist=False)


def test_file_copy_writes_under_allowed_base(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    src = tmp_path / "source.txt"
    src.write_text("hello", encoding="utf-8")

    dest = base / "copy.txt"
    sink = FileCopySink(destination=str(dest))
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    sink.prepare_artifacts({"in": [_make_artifact(src)]})
    sink.write({"results": []})
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "hello"


def test_file_copy_rejects_escape_outside_base(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    src = tmp_path / "source.txt"
    src.write_text("x", encoding="utf-8")

    # Destination outside allowed base should be rejected
    dest = tmp_path / "escape.txt"
    sink = FileCopySink(destination=str(dest))
    sink._allowed_base = outputs.resolve()  # type: ignore[attr-defined]
    sink.prepare_artifacts({"in": [_make_artifact(src)]})
    with pytest.raises(ValueError):
        sink.write({"results": []})


def test_file_copy_rejects_symlink_destination(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    src = tmp_path / "source.txt"
    src.write_text("x", encoding="utf-8")

    real_dest = base / "real.txt"
    real_dest.write_text("old", encoding="utf-8")
    link_dest = base / "link.txt"
    try:
        os.symlink(real_dest, link_dest)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/user")

    sink = FileCopySink(destination=str(link_dest))
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    sink.prepare_artifacts({"in": [_make_artifact(src)]})
    with pytest.raises(ValueError):
        sink.write({"results": []})

