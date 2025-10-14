"""Result sink that produces visual analytics artifacts."""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from elspeth.core.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.security import normalize_determinism_level, normalize_security_level

logger = logging.getLogger(__name__)


class VisualAnalyticsSink(ResultSink):
    """Render aggregate experiment metrics as PNG and/or HTML artifacts."""

    def __init__(
        self,
        *,
        base_path: str,
        file_stem: str = "analytics_visual",
        formats: Sequence[str] | None = None,
        dpi: int = 150,
        figure_size: Sequence[float] | None = None,
        include_table: bool = True,
        bar_color: str | None = None,
        chart_title: str | None = None,
        seaborn_style: str | None = "darkgrid",
        on_error: str = "abort",
    ) -> None:
        self.base_path = Path(base_path)
        self.file_stem = file_stem or "analytics_visual"
        selected: list[str] = []
        for fmt in formats or ["png"]:
            normalized = (fmt or "").strip().lower()
            if normalized in {"png", "html"}:
                selected.append(normalized)
        self.formats = selected or ["png"]
        if dpi <= 0:
            raise ValueError("dpi must be a positive integer")
        self.dpi = int(dpi)
        if figure_size:
            if len(figure_size) != 2:
                raise ValueError("figure_size must contain exactly two numeric values")
            width, height = figure_size
            if width <= 0 or height <= 0:
                raise ValueError("figure_size values must be positive numbers")
            self.figure_size: tuple[float, float] = (float(width), float(height))
        else:
            self.figure_size = (8.0, 4.5)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self.include_table = bool(include_table)
        self.bar_color = bar_color
        self.chart_title = chart_title or "Mean Scores by Criterion"
        self.seaborn_style = seaborn_style
        self._security_level: str | None = None
        self._determinism_level: str | None = None
        self._last_written_files: list[tuple[list[str], Path, dict[str, Any]]] = []
        self._plot_modules: tuple[Any, Any, Any] | None = None

    # --------------------------------------------------------------------- API
    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        try:
            score_means, pass_rates = self._extract_scores(results)
            if not score_means:
                logger.info("Visual analytics sink found no numeric scores; skipping output")
                self._last_written_files = []
                return
            _matplotlib, plt, seaborn = self._load_plot_modules()
        except Exception as exc:  # pragma: no cover - defensive guard
            if self.on_error == "skip":
                logger.warning("Visual analytics sink cannot initialise plotting backend; skipping output: %s", exc)
                return
            raise

        try:
            if seaborn is not None and self.seaborn_style:
                try:
                    seaborn.set_theme(style=self.seaborn_style)
                except Exception:
                    logger.debug("Seaborn style '%s' unavailable; using matplotlib defaults", self.seaborn_style)

            self.base_path.mkdir(parents=True, exist_ok=True)
            fig, ax = plt.subplots(figsize=self.figure_size)
            labels = list(score_means.keys())
            values = [score_means[label] for label in labels]
            bar_kwargs: dict[str, Any] = {}
            if self.bar_color:
                bar_kwargs["color"] = self.bar_color
            ax.bar(labels, values, **bar_kwargs)
            ax.set_ylabel("Mean Score")
            ax.set_xlabel("Criterion")
            ax.set_title(self.chart_title)
            if values:
                upper = max(values)
                ax.set_ylim(0, max(upper * 1.1, upper + 0.1))
            ax.tick_params(axis="x", rotation=45, labelrotation=45)
            for index, label in enumerate(labels):
                rate = pass_rates.get(label)
                if rate is not None:
                    ax.text(index, values[index], f"{rate*100:.1f}%", ha="center", va="bottom", fontsize=8)
            fig.tight_layout()

            buffer = io.BytesIO()
            fig.savefig(buffer, format="png", dpi=self.dpi)
            plt.close(fig)
            png_bytes = buffer.getvalue()

            written: list[tuple[list[str], Path, dict[str, Any]]] = []
            if "png" in self.formats:
                png_path = self.base_path / f"{self.file_stem}.png"
                png_path.write_bytes(png_bytes)
                written.append(
                    (
                        self._artifact_keys_for_format("png", png_path),
                        png_path,
                        {
                            "chart_data": score_means,
                            "pass_rates": pass_rates,
                        },
                    )
                )
            if "html" in self.formats:
                encoded = base64.b64encode(png_bytes).decode("ascii")
                html_path = self.base_path / f"{self.file_stem}.html"
                html_content = self._render_html(encoded, score_means, pass_rates, metadata)
                html_path.write_text(html_content, encoding="utf-8")
                written.append(
                    (
                        self._artifact_keys_for_format("html", html_path),
                        html_path,
                        {
                            "chart_data": score_means,
                            "pass_rates": pass_rates,
                        },
                    )
                )

            self._last_written_files = written
            if metadata:
                self._security_level = normalize_security_level(metadata.get("security_level"))
                self._determinism_level = normalize_determinism_level(metadata.get("determinism_level"))
            else:
                self._security_level = None
                self._determinism_level = None
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Visual analytics sink failed; skipping output: %s", exc)
                return
            raise

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - metadata only
        descriptors: list[ArtifactDescriptor] = []
        if "png" in self.formats:
            descriptors.append(
                ArtifactDescriptor(
                    name="analytics_visual_png",
                    type="image/png",
                    persist=True,
                    alias="analytics_visual",
                )
            )
        if "html" in self.formats:
            descriptors.append(
                ArtifactDescriptor(
                    name="analytics_visual_html",
                    type="text/html",
                    persist=True,
                    alias="analytics_visual_html",
                )
            )
        return descriptors

    def consumes(self) -> list[str]:  # pragma: no cover - no dependencies
        return []

    def collect_artifacts(self) -> dict[str, Artifact]:
        artifacts: dict[str, Artifact] = {}
        for keys, path, extra in self._last_written_files:
            suffix = path.suffix.lower()
            if suffix == ".png":
                content_type = "image/png"
            elif suffix == ".html":
                content_type = "text/html"
            else:  # pragma: no cover - defensive
                content_type = "application/octet-stream"
            metadata = {"path": str(path), "content_type": content_type}
            metadata.update(extra)
            artifact = Artifact(
                id="",
                type=content_type,
                path=str(path),
                metadata=metadata,
                persist=True,
                security_level=self._security_level,
                determinism_level=self._determinism_level,
            )
            for key in keys:
                artifacts[key] = artifact
        self._last_written_files = []
        return artifacts

    # ------------------------------------------------------------------ helpers
    def _load_plot_modules(self) -> tuple[Any, Any, Any]:
        if self._plot_modules is not None:
            return self._plot_modules
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError("matplotlib is required for the analytics_visual sink") from exc
        try:
            import seaborn
        except Exception:
            seaborn = None
        self._plot_modules = (matplotlib, plt, seaborn)
        return self._plot_modules

    def _extract_scores(self, payload: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
        means: dict[str, float] = {}
        pass_rates: dict[str, float] = {}
        aggregates = payload.get("aggregates")
        if isinstance(aggregates, Mapping):
            stats = aggregates.get("score_stats")
            if isinstance(stats, Mapping):
                criteria = stats.get("criteria")
                if isinstance(criteria, Mapping):
                    for name, entry in criteria.items():
                        if not isinstance(entry, Mapping):
                            continue
                        mean_value = entry.get("mean")
                        if mean_value is not None:
                            means[str(name)] = float(mean_value)
                        rate_value = entry.get("pass_rate")
                        if rate_value is not None:
                            pass_rates[str(name)] = float(rate_value)
        if means:
            return means, pass_rates

        # Fallback: compute from individual records
        score_lists: dict[str, list[float]] = {}
        flag_totals: dict[str, list[int]] = {}
        for record in payload.get("results") or []:
            if not isinstance(record, Mapping):
                continue
            metrics = record.get("metrics") or {}
            if isinstance(metrics, Mapping):
                scores = metrics.get("scores")
                if isinstance(scores, Mapping):
                    for name, value in scores.items():
                        try:
                            numeric = float(value)
                        except (TypeError, ValueError):
                            continue
                        score_lists.setdefault(str(name), []).append(numeric)
                flags = metrics.get("score_flags")
                if isinstance(flags, Mapping):
                    for name, passed in flags.items():
                        bucket = flag_totals.setdefault(str(name), [0, 0])
                        bucket[1] += 1
                        if passed:
                            bucket[0] += 1

        for name, values in score_lists.items():
            if values:
                means[name] = float(sum(values) / len(values))
        for name, totals in flag_totals.items():
            successes, attempts = totals
            if attempts:
                pass_rates[name] = successes / attempts
        return means, pass_rates

    def _artifact_keys_for_format(self, fmt: str, path: Path) -> list[str]:
        primary, alias = {
            "png": ("analytics_visual_png", "analytics_visual"),
            "html": ("analytics_visual_html", "analytics_visual_html"),
        }.get(fmt, (path.name, path.name))
        keys = [primary]
        if alias and alias != primary:
            keys.append(alias)
        keys.append(path.name)
        return keys

    def _render_html(
        self,
        encoded_png: str,
        means: Mapping[str, float],
        pass_rates: Mapping[str, float],
        metadata: Mapping[str, Any],
    ) -> str:
        table_html = ""
        if self.include_table and means:
            rows: list[str] = []
            for name, value in means.items():
                rate = pass_rates.get(name)
                rate_text = f"{rate*100:.1f}%" if rate is not None else "n/a"
                rows.append(f"<tr><td>{name}</td><td>{value:.4f}</td><td>{rate_text}</td></tr>")
            table_html = (
                "<table>"
                "<thead><tr><th>Criterion</th><th>Mean</th><th>Pass Rate</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody>"
                "</table>"
            )

        metadata_section = ""
        if metadata:
            items = []
            retry = metadata.get("retry_summary")
            if retry:
                items.append(f"<li><strong>Retry Summary:</strong> {retry}</li>")
            cost = metadata.get("cost_summary")
            if cost:
                items.append(f"<li><strong>Cost Summary:</strong> {cost}</li>")
            early_stop = metadata.get("early_stop")
            if early_stop:
                items.append(f"<li><strong>Early Stop:</strong> {early_stop}</li>")
            if items:
                metadata_section = "<ul>" + "".join(items) + "</ul>"

        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{self.chart_title}</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
      img {{ max-width: 100%; height: auto; }}
      table {{ border-collapse: collapse; margin-top: 1rem; }}
      th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: center; }}
      th {{ background-color: #f6f6f6; }}
    </style>
  </head>
  <body>
    <h1>{self.chart_title}</h1>
    <img src="data:image/png;base64,{encoded_png}" alt="Analytics chart" />
    {table_html}
    {metadata_section}
  </body>
</html>
"""


__all__ = ["VisualAnalyticsSink"]
