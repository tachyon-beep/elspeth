"""Shared path allowlist helpers for web subsystem.

AD-4: Single definitions used by composer tool validation,
execution validation, and execution runtime guards. Lives in
web/ (not composer/ or execution/) to avoid cross-package coupling.
"""

from __future__ import annotations

from pathlib import Path


def resolve_data_path(value: str, data_dir: str) -> Path:
    """Resolve a path value against data_dir (relative) or as-is (absolute).

    Relative paths are joined to data_dir before resolving; absolute paths
    are resolved directly.  Legacy blob-backed sources may carry storage
    paths like ``data/blobs/...`` when ``data_dir`` itself is the relative
    path ``data``.  Those paths already point inside data_dir from the
    process working directory, so return them as-is instead of producing a
    duplicated ``data/data/...`` path.  Traversal (``../``) is resolved by
    the OS — blocking traversals outside allowed directories is the caller's
    job (via the allowlist helpers below).
    """
    raw = Path(value)
    if raw.is_absolute():
        return raw.resolve()

    base = Path(data_dir).resolve()
    resolved_from_cwd = raw.resolve()
    if resolved_from_cwd.is_relative_to(base):
        return resolved_from_cwd

    return (base / raw).resolve()


def allowed_source_directories(data_dir: str) -> tuple[Path, ...]:
    """Return the set of directories from which source paths are allowed."""
    base = Path(data_dir).resolve()
    return (base / "blobs",)


def allowed_sink_directories(data_dir: str) -> tuple[Path, ...]:
    """Return the set of directories to which sink paths may write.

    Includes data_dir/outputs (primary sink target) and data_dir/blobs
    (output blobs are stored alongside input blobs).
    """
    base = Path(data_dir).resolve()
    return (base / "outputs", base / "blobs")
