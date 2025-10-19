from __future__ import annotations

import os
from pathlib import Path

from elspeth.core.utils.path_guard import safe_atomic_write


def test_safe_atomic_write_permission_hardening_branches(monkeypatch, tmp_path: Path):
    dest = tmp_path / "out.txt"

    calls = {"fchmod": 0, "chmod": 0}

    def boom_fchmod(fd, mode):  # noqa: D401
        calls["fchmod"] += 1
        raise OSError("fchmod not supported")

    def boom_chmod(path, mode):  # noqa: D401
        calls["chmod"] += 1
        raise OSError("chmod not supported")

    monkeypatch.setattr(os, "fchmod", boom_fchmod)
    monkeypatch.setattr(os, "chmod", boom_chmod)

    def writer(p: Path) -> None:
        p.write_text("ok", encoding="utf-8")

    safe_atomic_write(dest, writer)

    assert dest.read_text(encoding="utf-8") == "ok"
    assert calls["fchmod"] == 1
    assert calls["chmod"] == 1

