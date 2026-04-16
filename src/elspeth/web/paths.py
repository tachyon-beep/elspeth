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
    are resolved directly.  Traversal (``../``) is resolved by the OS —
    blocking traversals outside allowed directories is the caller's job
    (via the allowlist helpers below).
    """
    raw = Path(value)
    if raw.is_absolute():
        return raw.resolve()
    return (Path(data_dir).resolve() / raw).resolve()


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
