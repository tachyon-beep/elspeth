"""Sink that copies an input artifact to a destination path."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Mapping

from elspeth.core.base.protocols import Artifact, ResultSink
from elspeth.core.security import normalize_determinism_level, normalize_security_level
from elspeth.core.utils.path_guard import resolve_under_base, safe_atomic_write

logger = logging.getLogger(__name__)


class FileCopySink(ResultSink):
    def __init__(self, *, destination: str, overwrite: bool = True, on_error: str = "abort", allowed_base_path: str | None = None) -> None:
        self.destination = Path(destination)
        self.overwrite = overwrite
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self._source_artifact: Artifact | None = None
        self._written_path: Path | None = None
        self._output_type: str | None = None
        self._security_level: str | None = None
        self._determinism_level: str | None = None
        # Configure allowed base path for containment checks
        try:
            default_base = self.destination.parent.resolve()
            self._allowed_base = (
                Path(allowed_base_path).resolve() if allowed_base_path is not None else default_base
            )
        except Exception:  # pragma: no cover - defensive
            self._allowed_base = self.destination.parent.resolve()

    def prepare_artifacts(self, artifacts: Mapping[str, list[Artifact]]):  # pragma: no cover - optional
        self._source_artifact = None
        self._output_type = None
        for values in artifacts.values():
            if values:
                if len(values) > 1:
                    message = "FileCopySink supports a single input artifact; received multiple"
                    if self.on_error == "skip":
                        logger.warning(message)
                        self._source_artifact = values[0]
                        self._output_type = self._source_artifact.type
                        return
                    raise ValueError(message)
                self._source_artifact = values[0]
                self._output_type = self._source_artifact.type
                self._security_level = self._source_artifact.security_level
                return

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        if not self._source_artifact or not self._source_artifact.path:
            message = "FileCopySink requires an input artifact; configure artifacts.consumes"
            if self.on_error == "skip":
                logger.warning(message)
                return
            raise ValueError(message)

        src_path = Path(self._source_artifact.path)
        if not src_path.exists():
            message = f"Source artifact path not found: {src_path}"
            if self.on_error == "skip":
                logger.warning(message)
                return
            raise FileNotFoundError(message)

        if self.destination.exists() and not self.overwrite:
            raise FileExistsError(f"Destination exists: {self.destination}")

        # Resolve destination under allowed base (default to destination parent)
        default_base = self.destination.parent.resolve()
        allowed_base = getattr(self, "_allowed_base", None)
        base_to_use = allowed_base if allowed_base is not None else default_base
        target = resolve_under_base(self.destination, Path(base_to_use))
        plugin_logger = getattr(self, "plugin_logger", None)
        if plugin_logger:
            plugin_logger.log_event(
                "sink_write_attempt",
                message=f"File copy attempt: {src_path} -> {target}",
                metadata={"source": str(src_path), "dest": str(target)},
            )
        safe_atomic_write(target, lambda tmp: shutil.copyfile(src_path, tmp))
        self._written_path = target
        if plugin_logger:
            try:
                size = target.stat().st_size
            except Exception:
                size = 0
            plugin_logger.log_event(
                "sink_write",
                message=f"File copied to {target}",
                metrics={"bytes": size},
                metadata={"source": str(src_path), "dest": str(target)},
            )
        if metadata and metadata.get("security_level"):
            self._security_level = normalize_security_level(metadata.get("security_level"))
            self._determinism_level = normalize_determinism_level(metadata.get("determinism_level"))

    def collect_artifacts(self) -> dict[str, Artifact]:  # pragma: no cover - optional
        if not self._written_path:
            return {}
        metadata = {
            "source": self._source_artifact.id if self._source_artifact else None,
            "source_path": self._source_artifact.path if self._source_artifact else None,
            "security_level": self._security_level,
            "determinism_level": self._determinism_level,
        }
        if self._source_artifact and self._source_artifact.metadata:
            source_ct = self._source_artifact.metadata.get("content_type")
            if source_ct:
                metadata["content_type"] = source_ct
        artifact = Artifact(
            id="",
            type=self._output_type or "file/octet-stream",
            path=str(self._written_path),
            metadata=metadata,
            persist=True,
            security_level=self._security_level,
            determinism_level=self._determinism_level,
        )
        self._written_path = None
        self._source_artifact = None
        self._output_type = None
        self._security_level = None
        self._determinism_level = None
        return {"file": artifact}
