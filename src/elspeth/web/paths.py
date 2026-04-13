"""Shared path allowlist helpers for web subsystem.

AD-4: Single definitions used by composer tool validation,
execution validation, and execution runtime guards. Lives in
web/ (not composer/ or execution/) to avoid cross-package coupling.
"""

from __future__ import annotations

from pathlib import Path


def allowed_source_directories(data_dir: str) -> tuple[Path, ...]:
    """Return the set of directories from which source paths are allowed."""
    base = Path(data_dir).resolve()
    return (base / "blobs",)


def allowed_sink_directories(data_dir: str) -> tuple[Path, ...]:
    """Return the set of directories to which sink paths may write.

    Sinks write to data_dir/outputs (not blobs, which is for ingestion).
    """
    base = Path(data_dir).resolve()
    return (base / "outputs", base / "blobs")
