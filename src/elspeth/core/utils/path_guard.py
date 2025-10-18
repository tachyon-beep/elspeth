"""Path safety utilities for sink writes.

Guards against directory traversal and symlink attacks, and provides
atomic write helpers to avoid partial files on failure.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable


def resolve_under_base(target: Path, base: Path) -> Path:
    """Resolve `target` under `base` without following the final component.

    Ensures the parent directory of the destination is within the allowed base
    (preventing traversal), while leaving the final path component as-is so
    symlink checks can be applied explicitly downstream.
    """
    base_resolved = base.resolve()
    candidate = target if target.is_absolute() else base_resolved / target
    # Normalize dot segments without following symlinks
    candidate = Path(os.path.normpath(str(candidate)))
    parent_resolved = candidate.parent.resolve()

    try:
        common = Path(os.path.commonpath([str(base_resolved), str(parent_resolved)]))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid path resolution for target '{target}' under base '{base}'")

    if common != base_resolved:
        raise ValueError(f"Path parent '{parent_resolved}' escapes allowed base '{base_resolved}'")
    return parent_resolved / candidate.name


def ensure_no_symlinks_in_ancestors(path: Path) -> None:
    """Ensure no ancestor directory of `path` is a symlink.

    Raises:
        ValueError: If any ancestor is a symlink
    """
    p = path if path.is_dir() else path.parent
    for ancestor in [p, *p.parents]:
        # Skip filesystem root entries (their parent is themselves)
        if ancestor.parent == ancestor:
            continue
        # Path.is_symlink() uses lstat (does not follow the final component)
        if ancestor.is_symlink():
            raise ValueError(f"Symlinked ancestor not permitted: {ancestor}")


def ensure_destination_is_not_symlink(path: Path) -> None:
    """Reject symlink destination if it already exists.

    Raises:
        ValueError: If `path` exists and is a symlink
    """
    if path.exists() and path.is_symlink():
        raise ValueError(f"Refusing to write to symlink destination: {path}")


def check_and_prepare_dir(path: Path) -> None:
    """Create parent directories after verifying ancestors are not symlinks."""
    parent = path.parent
    ensure_no_symlinks_in_ancestors(parent)
    parent.mkdir(parents=True, exist_ok=True)


def safe_atomic_write(path: Path, write_to: Callable[[Path], None]) -> None:
    """Write via temp-file + atomic replace to avoid partial writes.

    Args:
        path: Final destination path
        write_to: Callback that receives a temporary file path to write to
    """
    check_and_prepare_dir(path)
    ensure_destination_is_not_symlink(path)

    # Create a temp file in the same directory to ensure atomic os.replace
    tmp_fd = None
    tmp_path_str = None
    try:
        tmp_fd, tmp_path_str = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
        tmp_path = Path(tmp_path_str)
        # Ensure owner-only permissions (0600) on the temporary file; mkstemp
        # already uses a safe default on POSIX, but we enforce explicitly.
        try:
            os.fchmod(tmp_fd, 0o600)
        except Exception:
            try:
                os.chmod(tmp_path, 0o600)
            except Exception:
                pass
        os.close(tmp_fd)
        tmp_fd = None

        write_to(tmp_path)

        # Best-effort fsync of directory after replace is handled by the OS in most cases.
        os.replace(tmp_path, path)
    finally:
        # Cleanup temp file if something went wrong
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except Exception:
                pass
        if tmp_path_str:
            try:
                tmp_p = Path(tmp_path_str)
                if tmp_p.exists():
                    tmp_p.unlink(missing_ok=True)
            except Exception:
                pass


__all__ = [
    "resolve_under_base",
    "ensure_no_symlinks_in_ancestors",
    "ensure_destination_is_not_symlink",
    "check_and_prepare_dir",
    "safe_atomic_write",
]
