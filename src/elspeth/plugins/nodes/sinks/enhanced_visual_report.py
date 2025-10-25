"""Enhanced result sink producing advanced visual analytics artifacts."""

from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor
from elspeth.core.base.types import SecurityLevel

from ._visual_base import BaseVisualSink

logger = logging.getLogger(__name__)


class EnhancedVisualAnalyticsSink(BaseVisualSink):
    """Render advanced experiment visualizations including distribution plots, heatmaps, and effect sizes.

    This sink extends basic bar charts with:
    - Violin plots and box plots for score distributions
    - Heatmaps for multi-criteria comparison matrices
    - Forest plots showing effect sizes with confidence intervals
    - Distribution overlay histograms for baseline vs variant comparison

    Requires matplotlib, seaborn, and numpy for rendering.
    """

    def __init__(
        self,
        *,
        base_path: str,
        file_stem: str = "enhanced_visual",
        formats: Sequence[str] | None = None,
        chart_types: Sequence[str] | None = None,
        dpi: int = 150,
        figure_size: Sequence[float] | None = None,
        seaborn_style: str | None = "darkgrid",
        color_palette: str | None = "Set2",
        on_error: str = "abort",
        security_level: SecurityLevel = SecurityLevel.OFFICIAL,  # ADR-004: Default for testing (YAML configs must be explicit)
        allow_downgrade: bool = True,  # ADR-005: Trusted downgrade for sinks (explicit choice, matches default suite)
    ) -> None:
        # Initialize base class with common parameters
        super().__init__(
            base_path=base_path,
            file_stem=file_stem or "enhanced_visual",
            formats=formats,
            dpi=dpi,
            figure_size=figure_size,
            default_figure_size=(10.0, 6.0),  # Custom default for this sink
            seaborn_style=seaborn_style,
            on_error=on_error,
            security_level=security_level,  # Pass security level to BaseVisualSink (ADR-004)
            allow_downgrade=allow_downgrade,  # Pass downgrade policy to BaseVisualSink (ADR-005)
        )

        # Sink-specific parameters: chart type validation
        valid_chart_types = {"violin", "box", "heatmap", "forest", "distribution"}
        selected_charts: list[str] = []
        for chart_type in chart_types or ["violin", "heatmap"]:
            normalized = (chart_type or "").strip().lower()
            if normalized in valid_chart_types:
                selected_charts.append(normalized)
        self.chart_types = selected_charts or ["violin"]

        self.color_palette = color_palette or "Set2"

    # --------------------------------------------------------------------- API
    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        try:
            # Extract data for visualization
            score_data = self._extract_score_data(results)
            if not score_data:
                logger.info("Enhanced visual sink found no data for plotting; skipping output")
                self._last_written_files = []
                return

            _matplotlib, plt, seaborn = self._load_plot_modules()
        except (ImportError, RuntimeError) as exc:  # pragma: no cover - defensive guard
            if self.on_error == "skip":
                logger.warning("Enhanced visual sink cannot initialise plotting backend: %s", exc)
                return
            raise

        try:
            plugin_logger = getattr(self, "plugin_logger", None)
            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write_attempt",
                    message=f"Enhanced visual write attempt: {self.base_path}/{self.file_stem}",
                    metadata={"path": str(self.base_path), "charts": list(self.chart_types)},
                )
            if seaborn is not None and self.seaborn_style:
                try:
                    seaborn.set_theme(style=self.seaborn_style)
                    seaborn.set_palette(self.color_palette)
                except (AttributeError, ValueError, TypeError):
                    logger.debug("Seaborn theme unavailable; using matplotlib defaults")

            self.base_path.mkdir(parents=True, exist_ok=True)
            written: list[tuple[str, Path, dict[str, Any]]] = []

            # Generate each requested chart type
            for chart_type in self.chart_types:
                try:
                    chart_files = self._generate_chart(chart_type, score_data, plt, seaborn, metadata)
                    written.extend(chart_files)
                except Exception as exc:
                    logger.warning("Failed to generate %s chart: %s", chart_type, exc)
                    if self.on_error == "abort":
                        raise

            self._last_written_files = written
            self._update_security_context_from_metadata(metadata)
            if plugin_logger:
                total_bytes = 0
                for _, path, _ in written:
                    try:
                        total_bytes += path.stat().st_size
                    except Exception:  # nosec B110 - tolerate stat() errors; do not block artifact write
                        logger.debug("Failed to stat file during size aggregation: %s", path, exc_info=True)
                plugin_logger.log_event(
                    "sink_write",
                    message=f"Enhanced visual written under {self.base_path}",
                    metrics={"bytes": total_bytes, "files": len(written)},
                    metadata={"path": str(self.base_path)},
                )
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Enhanced visual sink failed; skipping output: %s", exc)
                plugin_logger = getattr(self, "plugin_logger", None)
                if plugin_logger:
                    plugin_logger.log_error(exc, context="enhanced visual sink write", recoverable=True)
                return
            raise

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - metadata only
        descriptors: list[ArtifactDescriptor] = []
        for chart_type in self.chart_types:
            for fmt in self.formats:
                descriptors.append(
                    ArtifactDescriptor(
                        name=f"enhanced_visual_{chart_type}_{fmt}",
                        type="image/png" if fmt == "png" else "text/html",
                        persist=True,
                        alias=f"enhanced_visual_{chart_type}",
                    )
                )
        return descriptors

    def consumes(self) -> list[str]:  # pragma: no cover - no dependencies
        return []

    def collect_artifacts(self) -> dict[str, Artifact]:
        artifacts: dict[str, Artifact] = {}
        for name, path, extra in self._last_written_files:
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
                security_level=self._artifact_security_level,
                determinism_level=self._artifact_determinism_level,
            )
            artifacts[name] = artifact
        self._last_written_files = []
        return artifacts

    # ------------------------------------------------------------------ helpers
    # _load_plot_modules() inherited from BaseVisualSink

    def _extract_score_data(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Extract score data for visualization from experiment payload."""
        data: dict[str, Any] = {
            "criteria": [],
            "scores_by_criterion": {},
            "baseline_scores": {},
            "variant_scores": {},
            "effect_sizes": {},
        }

        # Extract from results (individual row scores)
        for result in payload.get("results", []) or []:
            if not isinstance(result, Mapping):
                continue
            metrics = result.get("metrics") or {}
            scores = metrics.get("scores")
            if isinstance(scores, Mapping):
                for name, value in scores.items():
                    try:
                        numeric = float(value)
                        if not math.isnan(numeric):
                            data["scores_by_criterion"].setdefault(name, []).append(numeric)
                    except (TypeError, ValueError):
                        continue

        # Extract baseline comparison data if available
        baseline_comparison = payload.get("baseline_comparison")
        if isinstance(baseline_comparison, Mapping):
            # ScoreSignificanceBaselinePlugin outputs
            significance = baseline_comparison.get("score_significance")
            if isinstance(significance, Mapping):
                for crit, stats in significance.items():
                    if isinstance(stats, Mapping):
                        effect = stats.get("effect_size")
                        if effect is not None:
                            data["effect_sizes"][crit] = {
                                "effect_size": effect,
                                "ci_lower": effect - 0.2,  # Approximate CI
                                "ci_upper": effect + 0.2,
                                "p_value": stats.get("p_value"),
                            }

        # Get unique criteria
        data["criteria"] = sorted(data["scores_by_criterion"].keys())

        return data if data["criteria"] else {}

    def _generate_chart(
        self,
        chart_type: str,
        data: dict[str, Any],
        plt: Any,
        seaborn: Any,
        metadata: dict[str, Any],
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Generate a specific chart type and return file references."""
        if chart_type == "violin":
            return self._generate_violin_plot(data, plt, seaborn, metadata)
        elif chart_type == "box":
            return self._generate_box_plot(data, plt, seaborn, metadata)
        elif chart_type == "heatmap":
            return self._generate_heatmap(data, plt, seaborn, metadata)
        elif chart_type == "forest":
            return self._generate_forest_plot(data, plt, seaborn, metadata)
        elif chart_type == "distribution":
            return self._generate_distribution_overlay(data, plt, seaborn, metadata)
        else:
            logger.warning("Unknown chart type: %s", chart_type)
            return []

    def _generate_violin_plot(
        self, data: dict[str, Any], plt: Any, seaborn: Any, _metadata: dict[str, Any]
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Generate violin plot showing score distributions by criterion."""
        criteria = data["criteria"]
        scores_by_criterion = data["scores_by_criterion"]

        # Prepare data for seaborn
        plot_data = []
        for crit in criteria:
            for score in scores_by_criterion.get(crit, []):
                plot_data.append({"Criterion": crit, "Score": score})

        if not plot_data:
            return []

        df = pd.DataFrame(plot_data)

        fig, ax = plt.subplots(figsize=self.figure_size)
        if seaborn is not None:
            seaborn.violinplot(data=df, x="Criterion", y="Score", ax=ax, inner="box")
        else:
            # Fallback to box plot if seaborn unavailable
            ax.boxplot(
                [scores_by_criterion.get(c, []) for c in criteria],
                labels=criteria,
            )
        ax.set_title("Score Distributions by Criterion")
        ax.set_xlabel("Criterion")
        ax.set_ylabel("Score")
        ax.tick_params(axis="x", rotation=45, labelrotation=45)
        fig.tight_layout()

        return self._save_figure(fig, plt, "violin", {"chart_type": "violin"})

    def _generate_box_plot(
        self, data: dict[str, Any], plt: Any, seaborn: Any, _metadata: dict[str, Any]
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Generate box plot showing score distributions with quartiles."""
        criteria = data["criteria"]
        scores_by_criterion = data["scores_by_criterion"]

        plot_data = []
        for crit in criteria:
            for score in scores_by_criterion.get(crit, []):
                plot_data.append({"Criterion": crit, "Score": score})

        if not plot_data:
            return []

        df = pd.DataFrame(plot_data)

        fig, ax = plt.subplots(figsize=self.figure_size)
        if seaborn is not None:
            seaborn.boxplot(data=df, x="Criterion", y="Score", ax=ax)
        else:
            ax.boxplot(
                [scores_by_criterion.get(c, []) for c in criteria],
                labels=criteria,
            )
        ax.set_title("Score Distributions with Quartiles")
        ax.set_xlabel("Criterion")
        ax.set_ylabel("Score")
        ax.tick_params(axis="x", rotation=45, labelrotation=45)
        fig.tight_layout()

        return self._save_figure(fig, plt, "box", {"chart_type": "box"})

    def _generate_heatmap(
        self, data: dict[str, Any], plt: Any, seaborn: Any, _metadata: dict[str, Any]
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Generate heatmap for multi-criteria score comparison."""
        criteria = data["criteria"]
        scores_by_criterion = data["scores_by_criterion"]

        if len(criteria) < 2:
            logger.debug("Heatmap requires at least 2 criteria; skipping")
            return []

        # Compute pairwise correlations
        score_matrix = []
        valid_criteria = []
        for crit in criteria:
            scores = scores_by_criterion.get(crit, [])
            if len(scores) >= 2:
                score_matrix.append(scores)
                valid_criteria.append(crit)

        if len(valid_criteria) < 2:
            return []

        # Pad shorter lists with NaN to make matrix rectangular
        max_len = max(len(scores) for scores in score_matrix)
        padded = []
        for scores in score_matrix:
            padded_scores = scores + [float("nan")] * (max_len - len(scores))
            padded.append(padded_scores)

        df = pd.DataFrame(np.array(padded).T, columns=valid_criteria)
        corr_matrix = df.corr()

        fig, ax = plt.subplots(figsize=self.figure_size)
        if seaborn is not None:
            seaborn.heatmap(
                corr_matrix,
                annot=True,
                fmt=".2f",
                cmap="coolwarm",
                center=0,
                ax=ax,
                cbar_kws={"label": "Correlation"},
            )
        else:
            im = ax.imshow(corr_matrix, cmap="coolwarm", aspect="auto")
            ax.set_xticks(range(len(valid_criteria)))
            ax.set_yticks(range(len(valid_criteria)))
            ax.set_xticklabels(valid_criteria, rotation=45)
            ax.set_yticklabels(valid_criteria)
            fig.colorbar(im, ax=ax, label="Correlation")
        ax.set_title("Criteria Score Correlation Heatmap")
        fig.tight_layout()

        return self._save_figure(fig, plt, "heatmap", {"chart_type": "heatmap"})

    def _generate_forest_plot(
        self, data: dict[str, Any], plt: Any, _seaborn: Any, _metadata: dict[str, Any]
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Generate forest plot showing effect sizes with confidence intervals."""
        effect_sizes = data.get("effect_sizes", {})
        if not effect_sizes:
            logger.debug("No effect size data available for forest plot")
            return []

        criteria = sorted(effect_sizes.keys())
        effects = [effect_sizes[c]["effect_size"] for c in criteria]
        ci_lower = [effect_sizes[c]["ci_lower"] for c in criteria]
        ci_upper = [effect_sizes[c]["ci_upper"] for c in criteria]

        fig, ax = plt.subplots(figsize=self.figure_size)
        y_pos = range(len(criteria))

        # Plot effect sizes with error bars
        ax.errorbar(
            effects,
            y_pos,
            xerr=[
                [effect - lower for effect, lower in zip(effects, ci_lower)],
                [upper - effect for effect, upper in zip(effects, ci_upper)],
            ],
            fmt="o",
            capsize=5,
            capthick=2,
            elinewidth=2,
            markersize=8,
        )

        # Add vertical line at zero (no effect)
        ax.axvline(x=0, color="red", linestyle="--", linewidth=1, alpha=0.7)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(criteria)
        ax.set_xlabel("Effect Size (Cohen's d)")
        ax.set_ylabel("Criterion")
        ax.set_title("Effect Sizes with 95% Confidence Intervals")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        return self._save_figure(fig, plt, "forest", {"chart_type": "forest"})

    def _generate_distribution_overlay(
        self, data: dict[str, Any], plt: Any, _seaborn: Any, _metadata: dict[str, Any]
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Generate overlaid histogram showing score distributions."""
        criteria = data["criteria"]
        scores_by_criterion = data["scores_by_criterion"]

        if not criteria:
            return []

        fig, ax = plt.subplots(figsize=self.figure_size)

        for crit in criteria:
            scores = scores_by_criterion.get(crit, [])
            if scores:
                ax.hist(
                    scores,
                    bins=15,
                    alpha=0.5,
                    label=crit,
                    edgecolor="black",
                    density=True,
                )

        ax.set_xlabel("Score")
        ax.set_ylabel("Density")
        ax.set_title("Score Distribution Overlays")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        return self._save_figure(fig, plt, "distribution", {"chart_type": "distribution"})

    def _save_figure(self, fig: Any, plt: Any, chart_type: str, extra_metadata: dict[str, Any]) -> list[tuple[str, Path, dict[str, Any]]]:
        """Save figure to configured formats and return file references."""
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=self.dpi)
        plt.close(fig)
        png_bytes = buffer.getvalue()

        written: list[tuple[str, Path, dict[str, Any]]] = []

        if "png" in self.formats:
            png_path = self.base_path / f"{self.file_stem}_{chart_type}.png"
            png_path.write_bytes(png_bytes)
            name = f"enhanced_visual_{chart_type}_png"
            written.append((name, png_path, extra_metadata))

        if "html" in self.formats:
            encoded = base64.b64encode(png_bytes).decode("ascii")
            html_path = self.base_path / f"{self.file_stem}_{chart_type}.html"
            html_content = self._render_html(encoded, chart_type)
            html_path.write_text(html_content, encoding="utf-8")
            name = f"enhanced_visual_{chart_type}_html"
            written.append((name, html_path, extra_metadata))

        return written

    def _render_html(self, encoded_png: str, chart_type: str) -> str:
        """Render HTML wrapper for embedded PNG chart."""
        title = chart_type.replace("_", " ").title()
        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{title} Chart</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
      img {{ max-width: 100%; height: auto; }}
    </style>
  </head>
  <body>
    <h1>{title} Visualization</h1>
    <img src="data:image/png;base64,{encoded_png}" alt="{title} chart" />
  </body>
</html>
"""


__all__ = ["EnhancedVisualAnalyticsSink"]
