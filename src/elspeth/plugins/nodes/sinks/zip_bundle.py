"""Result sink that archives experiment outputs into a ZIP bundle."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from elspeth.core.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.security import normalize_determinism_level, normalize_security_level, resolve_security_level
from elspeth.plugins.nodes.sinks._sanitize import sanitize_cell

logger = logging.getLogger(__name__)


class ZipResultSink(ResultSink):
    """Bundle results, manifest, and optional CSV into a compressed archive."""

    def __init__(
        self,
        *,
        base_path: str | Path,
        bundle_name: str | None = None,
        timestamped: bool = True,
        include_manifest: bool = True,
        include_results: bool = True,
        include_csv: bool = False,
        manifest_name: str = "manifest.json",
        results_name: str = "results.json",
        csv_name: str = "results.csv",
        on_error: str = "abort",
        sanitize_formulas: bool = True,
        sanitize_guard: str = "'",
    ) -> None:
        self.base_path = Path(base_path)
        self.bundle_name = bundle_name
        self.timestamped = timestamped
        self.include_manifest = include_manifest
        self.include_results = include_results
        self.include_csv = include_csv
        self.manifest_name = manifest_name
        self.results_name = results_name
        self.csv_name = csv_name
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        if not sanitize_guard:
            sanitize_guard = "'"
        if len(sanitize_guard) != 1:
            raise ValueError("sanitize_guard must be a single character")
        self.sanitize_formulas = sanitize_formulas
        self.sanitize_guard = sanitize_guard
        if not self.sanitize_formulas:
            logger.warning("ZIP sink sanitization disabled; CSV artifacts may trigger formulas.")
        self._sanitization = {
            "enabled": self.sanitize_formulas,
            "guard": self.sanitize_guard,
        }
        self._last_archive_path: str | None = None
        self._last_artifacts: dict[str, Any] = {}
        self._additional_inputs: dict[str, list[Artifact]] = {}
        self._security_level: str | None = None
        self._determinism_level: str | None = None

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        try:
            archive_path = self._resolve_path(metadata, timestamp)
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as bundle:
                if self.include_results:
                    payload = json.dumps(results, indent=2, sort_keys=True)
                    bundle.writestr(self.results_name, payload)

                if self.include_manifest:
                    manifest = self._build_manifest(results, metadata, timestamp)
                    bundle.writestr(
                        self.manifest_name,
                        json.dumps(manifest, indent=2, sort_keys=True),
                    )

                if self.include_csv:
                    csv_data = self._render_csv(results)
                    bundle.writestr(self.csv_name, csv_data)

                # Include upstream artifacts
                counter = 0
                for key, artifacts in self._additional_inputs.items():
                    for artifact in artifacts:
                        counter += 1
                        name = None
                        if artifact.metadata:
                            name = artifact.metadata.get("filename") or artifact.metadata.get("path")
                            if name and Path(name).is_absolute():
                                name = Path(name).name
                        if not name and artifact.path:
                            name = Path(artifact.path).name
                        if not name:
                            name = f"artifact_{counter}"
                        data = self._read_artifact(artifact)
                        bundle.writestr(name, data)
            self._last_archive_path = str(archive_path)
            self._last_artifacts = {
                "results": self.results_name if self.include_results else None,
                "manifest": self.manifest_name if self.include_manifest else None,
                "csv": self.csv_name if self.include_csv else None,
                "sanitization": self._sanitization,
            }
            if metadata:
                self._security_level = normalize_security_level(metadata.get("security_level"))
                self._determinism_level = normalize_determinism_level(metadata.get("determinism_level"))
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("ZIP sink failed; skipping archive creation: %s", exc)
                return
            raise
        finally:
            self._additional_inputs = {}

    def _sanitize_key(self, key: Any) -> Any:
        if not self.sanitize_formulas or not isinstance(key, str):
            return key
        return sanitize_cell(key, guard=self.sanitize_guard)

    def _sanitize_value(self, value: Any) -> Any:
        if not self.sanitize_formulas:
            return value
        return sanitize_cell(value, guard=self.sanitize_guard)

    # ------------------------------------------------------------------ helpers
    def _resolve_path(self, metadata: Mapping[str, Any], timestamp: datetime) -> Path:
        name = self.bundle_name or str(metadata.get("experiment") or metadata.get("name") or "experiment")
        if self.timestamped:
            name = f"{name}_{timestamp.strftime('%Y%m%dT%H%M%SZ')}"
        return self.base_path / f"{name}.zip"

    def _build_manifest(
        self,
        results: Mapping[str, Any],
        metadata: Mapping[str, Any],
        timestamp: datetime,
    ) -> dict[str, Any]:
        manifest = {
            "generated_at": timestamp.isoformat(),
            "rows": (len(results.get("results", [])) if isinstance(results.get("results"), list) else 0),
            "metadata": dict(metadata),
            "sanitization": self._sanitization,
        }
        if "aggregates" in results:
            manifest["aggregates"] = results["aggregates"]
        if "cost_summary" in results:
            manifest["cost_summary"] = results["cost_summary"]
        if "failures" in results:
            manifest["failures"] = results["failures"]
        return manifest

    def _render_csv(self, results: Mapping[str, Any]) -> str:
        entries = results.get("results", [])
        if not entries:
            return ""
        rows: list[dict[Any, Any]] = []
        for item in entries:
            record: dict[Any, Any] = {}
            row_data = item.get("row", {}) if isinstance(item, Mapping) else {}
            if isinstance(row_data, Mapping):
                for key, value in row_data.items():
                    record[self._sanitize_key(key)] = self._sanitize_value(value)
            response = item.get("response", {}) if isinstance(item, Mapping) else {}
            if isinstance(response, Mapping):
                record[self._sanitize_key("llm_content")] = self._sanitize_value(response.get("content"))
            responses = item.get("responses") if isinstance(item, Mapping) else None
            if isinstance(responses, Mapping):
                for name, resp in responses.items():
                    if isinstance(resp, Mapping):
                        record[self._sanitize_key(f"llm_{name}")] = self._sanitize_value(resp.get("content"))
            rows.append(record)
        df = pd.DataFrame(rows)
        if not df.empty:
            df.columns = [self._sanitize_key(col) for col in df.columns]
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        return buffer.getvalue()

    def produces(self):  # pragma: no cover - placeholder for artifact chaining
        return [
            ArtifactDescriptor(name="zip", type="file/zip", persist=True, alias="zip"),
        ]

    def consumes(self):  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(self, artifacts, *, metadata=None):  # pragma: no cover - optional cleanup
        return None

    def collect_artifacts(self) -> dict[str, Artifact]:  # pragma: no cover
        if not self._last_archive_path:
            return {}
        metadata = {key: value for key, value in self._last_artifacts.items() if value}
        metadata["security_level"] = self._security_level
        metadata["determinism_level"] = self._determinism_level
        artifact = Artifact(
            id="",
            type="file/zip",
            path=self._last_archive_path,
            metadata=metadata,
            persist=True,
            security_level=self._security_level,
            determinism_level=self._determinism_level,
        )
        self._last_archive_path = None
        self._last_artifacts = {}
        self._security_level = None
        self._determinism_level = None
        return {"zip": artifact}

    def prepare_artifacts(self, artifacts: Mapping[str, list[Artifact]]):  # pragma: no cover
        self._additional_inputs = {key: list(values) for key, values in artifacts.items() if values}
        if not self._security_level and self._additional_inputs:
            levels = [artifact.security_level for values in self._additional_inputs.values() for artifact in values]
            self._security_level = resolve_security_level(*levels)

    @staticmethod
    def _read_artifact(artifact: Artifact) -> bytes:
        if artifact.path:
            return Path(artifact.path).read_bytes()
        if artifact.payload is not None:
            payload = artifact.payload
            if isinstance(payload, (bytes, bytearray)):
                return bytes(payload)
            if hasattr(payload, "read"):
                # File-like object .read() method returns Any without protocol type stub
                return payload.read()  # type: ignore[no-any-return]
            return json.dumps(payload).encode("utf-8")
        raise ValueError("Artifact is missing payload data")


__all__ = ["ZipResultSink"]
