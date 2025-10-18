from __future__ import annotations

import os
from pathlib import Path

import pytest

from elspeth.core.utils.path_guard import (
    ensure_destination_is_not_symlink,
    ensure_no_symlinks_in_ancestors,
    resolve_under_base,
    safe_atomic_write,
)


def test_resolve_under_base_valid(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    target = Path("sub/dir/file.txt")
    resolved = resolve_under_base(target, base)
    assert str(resolved).startswith(str(base.resolve()))


def test_resolve_under_base_rejects_escape(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    target = Path("../escape.txt")
    with pytest.raises(ValueError):
        resolve_under_base(target, base)


def test_symlink_ancestor_rejection(tmp_path: Path) -> None:
    # Some platforms (Windows) require privileges for symlink creation
    target_dir = tmp_path / "real"
    target_dir.mkdir()
    link_parent = tmp_path / "link"
    try:
        os.symlink(target_dir, link_parent)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported by platform/user")

    victim = link_parent / "child" / "file.txt"
    with pytest.raises(ValueError):
        ensure_no_symlinks_in_ancestors(victim)


def test_safe_atomic_write(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    dest = base / "data.csv"

    def _writer(p: Path) -> None:
        p.write_text("hello,world\n", encoding="utf-8")

    safe_atomic_write(dest, _writer)
    assert dest.exists()
    assert dest.read_text(encoding="utf-8").startswith("hello,world")


def test_destination_symlink_rejected(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    real = base / "real.txt"
    real.write_text("ok", encoding="utf-8")
    link = base / "link.txt"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported by platform/user")

    with pytest.raises(ValueError):
        ensure_destination_is_not_symlink(link)
