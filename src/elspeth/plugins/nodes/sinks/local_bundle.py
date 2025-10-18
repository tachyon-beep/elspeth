"""Filesystem bundle sink for archiving experiment outputs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.utils.path_guard import resolve_under_base, safe_atomic_write
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink

logger = logging.getLogger(__name__)


@dataclass
class LocalBundleSink(ResultSink):
    base_path: str | Path
    bundle_name: str | None = None
    timestamped: bool = True
    write_json: bool = True
    write_csv: bool = False
    manifest_name: str = "manifest.json"
    results_name: str = "results.json"
    csv_name: str = "results.csv"
    on_error: str = "abort"
    sanitize_formulas: bool = True
    sanitize_guard: str = "'"

    allowed_base_path: str | None = None

    def __post_init__(self) -> None:
        self.base_path: Path = Path(self.base_path)
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        if not self.sanitize_guard:
            self.sanitize_guard = "'"
        if len(self.sanitize_guard) != 1:
            raise ValueError("sanitize_guard must be a single character")
        if not self.sanitize_formulas:
            logger.warning("Local bundle CSV sanitization disabled; outputs may trigger spreadsheet formulas.")
        # Allowed base directory for writes; default to ./outputs
        try:
            default_base = Path(self.base_path).resolve()
            self._allowed_base = Path(self.allowed_base_path).resolve() if self.allowed_base_path else default_base
        except Exception:  # pragma: no cover - defensive; nosec B110
            self._allowed_base = Path.cwd().resolve()

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        try:
            plugin_logger = getattr(self, "plugin_logger", None)
            bundle_dir = self._resolve_bundle_dir(metadata, timestamp)
            # Enforce allowed base for directory; use placeholder technique to leverage resolver
            target_dir = resolve_under_base(bundle_dir / ".dir", self._allowed_base).parent

            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write_attempt",
                    message=f"Bundle write attempt: {target_dir}",
                    metadata={"path": str(target_dir)},
                )

            manifest = self._build_manifest(results, metadata, timestamp)
            manifest_path = target_dir / self.manifest_name

            def _write_manifest(tmp: Path) -> None:
                tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

            safe_atomic_write(manifest_path, _write_manifest)

            if self.write_json:
                results_path = target_dir / self.results_name

                def _write_results(tmp: Path) -> None:
                    tmp.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

                safe_atomic_write(results_path, _write_results)

            if self.write_csv:
                csv_path = target_dir / self.csv_name
                csv_sink = CsvResultSink(
                    path=str(csv_path),
                    overwrite=True,
                    sanitize_formulas=self.sanitize_formulas,
                    sanitize_guard=self.sanitize_guard,
                )
                # Propagate allowed base to nested sink
                try:
                    csv_sink._allowed_base = self._allowed_base
                except Exception:  # nosec B110 - optional optimization only
                    pass
                csv_sink.write(results, metadata=metadata)

            if plugin_logger:
                total_bytes = 0
                paths: list[Path | None] = [
                    manifest_path,
                    (target_dir / self.results_name) if self.write_json else None,
                    (target_dir / self.csv_name) if self.write_csv else None,
                ]
                for p in paths:
                    if p and p.exists():
                        try:
                            total_bytes += p.stat().st_size
                        except Exception:  # nosec B110 - tolerate stat() errors; do not block artifact write
                            pass
                plugin_logger.log_event(
                    "sink_write",
                    message=f"Bundle written under {target_dir}",
                    metrics={"bytes": total_bytes},
                    metadata={"path": str(target_dir)},
                )
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Local bundle sink failed; skipping bundle creation: %s", exc)
                plugin_logger = getattr(self, "plugin_logger", None)
                if plugin_logger:
                    plugin_logger.log_error(exc, context="local bundle sink write", recoverable=True)
                return
            raise

    # ------------------------------------------------------------------ helpers
    def _resolve_bundle_dir(self, metadata: dict[str, Any], timestamp: datetime) -> Path:
        name = self.bundle_name or str(metadata.get("experiment") or metadata.get("name") or "experiment")
        if self.timestamped:
            stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
            name = f"{name}_{stamp}"
        # base_path is guaranteed to be Path after __post_init__
        return Path(self.base_path) / name

    def _build_manifest(self, results: dict[str, Any], metadata: dict[str, Any], timestamp: datetime) -> dict[str, Any]:
        manifest = {
            "generated_at": timestamp.isoformat(),
            "rows": len(results.get("results", [])),
            "metadata": metadata,
            "sanitization": {
                "enabled": self.sanitize_formulas,
                "guard": self.sanitize_guard,
            },
        }
        if "aggregates" in results:
            manifest["aggregates"] = results["aggregates"]
        if "cost_summary" in results:
            manifest["cost_summary"] = results["cost_summary"]
        if results.get("results"):
            manifest["columns"] = sorted({key for row in results["results"] for key in row.get("row", {}).keys()})
        return manifest

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - placeholder for artifact chaining
        return []

    def consumes(self) -> list[str]:  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(
        self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None
    ) -> None:  # pragma: no cover - optional cleanup
        return None
