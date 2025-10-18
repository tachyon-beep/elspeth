import os
import tempfile
from pathlib import Path

import pytest

from elspeth.core.utils.path_guard import (
    ensure_destination_is_not_symlink,
    ensure_no_symlinks_in_ancestors,
    resolve_under_base,
    safe_atomic_write,
)


def test_resolve_under_base_prevents_traversal(tmp_path: Path):
    base = tmp_path / "base"
    (base / "out").mkdir(parents=True)
    target = Path("../etc/passwd")
    with pytest.raises(ValueError):
        resolve_under_base(target, base / "out")


def test_symlink_ancestors_rejected(tmp_path: Path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    symlink_dir = tmp_path / "link"
    symlink_dir.symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(ValueError):
        ensure_no_symlinks_in_ancestors(symlink_dir / "file.txt")


def test_destination_symlink_rejected(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    dest = base / "file.txt"
    # Create a separate real file and link to it at dest
    real = base / "real.txt"
    real.write_text("x", encoding="utf-8")
    dest.symlink_to(real)
    with pytest.raises(ValueError):
        ensure_destination_is_not_symlink(dest)


def test_safe_atomic_write_success_and_failure(tmp_path: Path):
    out = tmp_path / "out.txt"

    def writer_ok(p: Path) -> None:
        p.write_text("hello", encoding="utf-8")

    safe_atomic_write(out, writer_ok)
    assert out.read_text(encoding="utf-8") == "hello"

    # Failure path: writer raises; destination should not be created
    out2 = tmp_path / "out2.txt"

    def writer_fail(p: Path) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        safe_atomic_write(out2, writer_fail)
    assert not out2.exists()

