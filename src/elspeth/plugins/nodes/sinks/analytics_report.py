"""Result sink that emits structured analytics summaries."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.core.security import ensure_determinism_level, ensure_security_level

logger = logging.getLogger(__name__)


class AnalyticsReportSink(ResultSink):
    """Generate a JSON analytics report (and optional Markdown) summarizing results and failures."""

    def __init__(
        self,
        *,
        base_path: str,
        file_stem: str = "analytics_report",
        formats: Sequence[str] | None = None,
        include_metadata: bool = True,
        include_aggregates: bool = True,
        include_comparisons: bool = True,
        on_error: str = "abort",
    ) -> None:
        self.base_path = Path(base_path)
        self.file_stem = file_stem or "analytics_report"
        selected = []
        for fmt in formats or ["json", "md"]:
            normalized = (fmt or "").strip().lower()
            if normalized == "markdown":
                normalized = "md"
            if normalized:
                selected.append(normalized)
        self.formats = [fmt for fmt in selected if fmt in {"json", "md"}] or ["json"]
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self.include_metadata = include_metadata
        self.include_aggregates = include_aggregates
        self.include_comparisons = include_comparisons
        self._last_written_files: list[Path] = []
        self._security_level: SecurityLevel | None = None
        self._determinism_level: DeterminismLevel | None = None

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        try:
            summary = self._build_summary(results, metadata or {})
            self.base_path.mkdir(parents=True, exist_ok=True)
            plugin_logger = getattr(self, "plugin_logger", None)
            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write_attempt",
                    message=f"Analytics report write attempt: {self.base_path}/{self.file_stem}",
                    metrics={"rows": summary.get("rows", 0)},
                    metadata={"path": str(self.base_path)},
                )
            written: list[Path] = []
            if "json" in self.formats:
                path = self.base_path / f"{self.file_stem}.json"
                path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
                written.append(path)
            if "md" in self.formats:
                path = self.base_path / f"{self.file_stem}.md"
                path.write_text(self._render_markdown(summary), encoding="utf-8")
                written.append(path)
            self._last_written_files = written
            if metadata:
                level = metadata.get("security_level")
                det = metadata.get("determinism_level")
                self._security_level = level if isinstance(level, SecurityLevel) else ensure_security_level(level)
                self._determinism_level = det if isinstance(det, DeterminismLevel) else ensure_determinism_level(det)
            if plugin_logger:
                total_bytes = 0
                for p in written:
                    try:
                        total_bytes += p.stat().st_size
                    except (OSError, PermissionError):  # tolerate stat() errors to avoid blocking artifact write
                        pass
                plugin_logger.log_event(
                    "sink_write",
                    message=f"Analytics report written under {self.base_path}",
                    metrics={"bytes": total_bytes, "files": len(written)},
                    metadata={"path": str(self.base_path)},
                )
        except Exception as exc:  # pragma: no cover - error handling path (render/write)
            if self.on_error == "skip":
                logger.warning("Analytics report sink failed; skipping write: %s", exc)
                plugin_logger = getattr(self, "plugin_logger", None)
                if plugin_logger:
                    plugin_logger.log_error(exc, context="analytics report sink write", recoverable=True)
                return
            raise

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - metadata only
        return [
            ArtifactDescriptor(name="analytics_report", type="file/json", persist=True, alias="analytics"),
        ]

    def consumes(self) -> list[str]:  # pragma: no cover - no dependencies
        return []

    def collect_artifacts(self) -> dict[str, Artifact]:
        artifacts: dict[str, Artifact] = {}
        for path in self._last_written_files:
            content_type = "application/json" if path.suffix == ".json" else "text/markdown"
            artifacts[path.name] = Artifact(
                id="",
                type=content_type,
                path=str(path),
                metadata={"path": str(path), "content_type": content_type},
                persist=True,
                security_level=self._security_level,
                determinism_level=self._determinism_level,
            )
        self._last_written_files = []
        return artifacts

    def _build_summary(self, payload: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
        results = list(payload.get("results") or [])
        failures = list(payload.get("failures") or [])
        summary: dict[str, Any] = {
            "rows": len(results),
            "failures": len(failures),
        }
        if len(failures) > 0:
            summary["failure_examples"] = failures[: min(len(failures), 5)]
        payload_meta = payload.get("metadata") or {}
        if self.include_metadata:
            summary["metadata"] = {
                "retry_summary": payload_meta.get("retry_summary"),
                "early_stop": payload_meta.get("early_stop"),
                "cost_summary": payload_meta.get("cost_summary"),
                "security_level": payload_meta.get("security_level"),
                "determinism_level": payload_meta.get("determinism_level"),
            }
        if self.include_aggregates and payload.get("aggregates"):
            summary["aggregates"] = payload["aggregates"]
        if self.include_comparisons:
            summary["baseline_comparison"] = payload.get("baseline_comparison")
        analytics_sections = {}
        for key in (
            "score_cliffs_delta",
            "score_assumptions",
            "score_practical",
            "score_distribution",
            "score_significance",
            "score_power",
        ):
            value = payload.get(key)
            if value:
                analytics_sections[key] = value
        if analytics_sections:
            summary["analytics"] = analytics_sections
        return summary

    def _render_markdown(self, summary: Mapping[str, Any]) -> str:
        lines: list[str] = ["# Analytics Report", ""]
        lines.append(f"- **Rows processed:** {summary.get('rows', 0)}")
        failures = summary.get("failures", 0)
        if failures:
            lines.append(f"- **Failures:** {failures}")
        metadata = summary.get("metadata") or {}
        if metadata.get("early_stop"):
            lines.append(f"- **Early stop:** {json.dumps(metadata['early_stop'])}")
        if metadata.get("cost_summary"):
            lines.append(f"- **Cost summary:** {json.dumps(metadata['cost_summary'])}")
        lines.append("")

        aggregates = summary.get("aggregates")
        if aggregates:
            lines.extend(["## Aggregates", "```json", json.dumps(aggregates, indent=2, sort_keys=True), "```", ""])

        baseline_comparison = summary.get("baseline_comparison")
        if baseline_comparison:
            lines.extend(
                [
                    "## Baseline Comparison",
                    "```json",
                    json.dumps(baseline_comparison, indent=2, sort_keys=True),
                    "```",
                    "",
                ]
            )

        analytics = summary.get("analytics") or {}
        if analytics:
            lines.append("## Analytics")
            for name, value in analytics.items():
                lines.extend(
                    [
                        f"### {name}",
                        "```json",
                        json.dumps(value, indent=2, sort_keys=True),
                        "```",
                        "",
                    ]
                )

        if summary.get("failure_examples"):
            lines.extend(
                [
                    "## Failure Examples",
                    "```json",
                    json.dumps(summary["failure_examples"], indent=2, sort_keys=True),
                    "```",
                    "",
                ]
            )
        return "\n".join(lines)
