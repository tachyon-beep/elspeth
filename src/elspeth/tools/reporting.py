"""Suite reporting utilities producing consolidated artefacts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.tools import export_suite_configuration, summarize_suite
from elspeth.core.validation import validate_suite

logger = logging.getLogger(__name__)


class SuiteReportGenerator:
    """Generate markdown, Excel, and visual summaries for suite runs."""

    def __init__(self, suite: ExperimentSuite, results: Mapping[str, Mapping[str, Any]]) -> None:
        self.suite = suite
        self.results = results
        self.baseline_name = suite.baseline.name if suite.baseline else None

    def generate_all_reports(self, output_root: Path | str) -> None:
        root = Path(output_root)
        consolidated = root / "consolidated"
        consolidated.mkdir(parents=True, exist_ok=True)

        logger.info("Generating suite reports in %s", consolidated)

        validation = validate_suite(self.suite.root)
        validation_path = consolidated / "validation_results.json"
        validation_path.write_text(
            json.dumps(
                {
                    "errors": [msg.format() for msg in validation.report.errors],
                    "warnings": [msg.format() for msg in validation.report.warnings],
                    "preflight": validation.preflight,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        self._generate_individual_stats(root)
        comparative = self._generate_comparative(consolidated)
        recommendations = self._generate_recommendations(consolidated)
        self._export_analysis_config(consolidated)
        self._generate_failure_report(consolidated)
        self._generate_executive_summary(consolidated, comparative, recommendations)
        self._generate_excel_report(consolidated, comparative, recommendations)
        self._generate_visualizations(consolidated, comparative)

    # ------------------------------------------------------------------ helpers

    def _generate_individual_stats(self, output_root: Path) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        for name, entry in self.results.items():
            payload = entry.get("payload")
            if not payload:
                continue
            exp_dir = output_root / name
            exp_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "experiment": name,
                "row_count": len(payload.get("results", [])),
                "failures": len(payload.get("failures", [])),
                "aggregates": payload.get("aggregates"),
                "config": self._config_dict(entry.get("config")),
                "timestamp": timestamp,
            }
            (exp_dir / "stats.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _generate_comparative(self, consolidated: Path) -> dict[str, Any]:
        baseline_payload = None
        if self.baseline_name:
            baseline_payload = self.results.get(self.baseline_name, {}).get("payload")
        comparative: dict[str, Any] = {
            "baseline": self.baseline_name,
            "baseline_stats": self._summaries_from_payload(baseline_payload),
            "variants": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        for name, entry in self.results.items():
            if name == self.baseline_name:
                continue
            payload = entry.get("payload")
            if not payload:
                continue
            comparative["variants"][name] = {
                "stats": self._summaries_from_payload(payload),
                "comparisons": entry.get("baseline_comparison"),
            }
        (consolidated / "comparative_analysis.json").write_text(json.dumps(comparative, indent=2), encoding="utf-8")
        return comparative

    def _generate_recommendations(self, consolidated: Path) -> dict[str, Any]:
        recommendations: dict[str, Any] = {}
        for name, entry in self.results.items():
            payload = entry.get("payload") or {}
            aggregates = payload.get("aggregates") or {}
            candidate = aggregates.get("score_recommendation") or {}
            ranking = aggregates.get("score_variant_ranking") or {}
            if candidate or ranking:
                recommendations[name] = {
                    "recommendation": candidate,
                    "ranking": ranking,
                }
        (consolidated / "recommendations.json").write_text(json.dumps(recommendations, indent=2), encoding="utf-8")
        return recommendations

    def _export_analysis_config(self, consolidated: Path) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "suite": summarize_suite(self.suite),
            "plugin_summary": self._collect_plugin_summary(),
        }
        (consolidated / "analysis_config.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        export_suite_configuration(self.suite, consolidated / "suite_export.json")

    def _collect_plugin_summary(self) -> dict[str, Any]:
        row_plugins = set()
        agg_plugins = set()
        baseline_plugins = set()
        middleware = set()
        for config in self.suite.experiments:
            for entry in config.row_plugin_defs:
                name = entry.get("name")
                if name:
                    row_plugins.add(name)
            for entry in config.aggregator_plugin_defs:
                name = entry.get("name")
                if name:
                    agg_plugins.add(name)
            for entry in config.baseline_plugin_defs:
                name = entry.get("name")
                if name:
                    baseline_plugins.add(name)
            for entry in config.llm_middleware_defs:
                name = entry.get("name") or entry.get("plugin")
                if name:
                    middleware.add(name)
        return {
            "row_plugins": sorted(row_plugins),
            "aggregator_plugins": sorted(agg_plugins),
            "baseline_plugins": sorted(baseline_plugins),
            "llm_middlewares": sorted(middleware),
        }

    def _generate_failure_report(self, consolidated: Path) -> None:
        records = {}
        for name, entry in self.results.items():
            failures = entry.get("payload", {}).get("failures")
            if failures:
                records[name] = failures
        (consolidated / "failure_analysis.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    def _generate_executive_summary(
        self,
        consolidated: Path,
        comparative: dict[str, Any],
        recommendations: dict[str, Any],
    ) -> None:
        lines = ["# Executive Summary", ""]
        lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
        baseline = comparative.get("baseline")
        if baseline:
            baseline_stats = comparative.get("baseline_stats") or {}
            baseline_mean = baseline_stats.get("overall", {}).get("mean")
            if baseline_mean is not None:
                lines.append(f"- Baseline: **{baseline}** (mean score {baseline_mean:.2f})")
            else:
                lines.append(f"- Baseline: **{baseline}**")
        lines.append("")
        lines.append("## Variant Highlights")
        variants = comparative.get("variants", {})
        if not variants:
            lines.append("No variants available for comparison.")
        else:
            scored = []
            for name, payload in variants.items():
                mean = _safe_get(payload.get("stats"), ("overall", "mean"))
                scored.append((name, mean))
            scored.sort(key=lambda item: item[1] if item[1] is not None else float("-inf"), reverse=True)
            for name, mean in scored:
                recommendation = recommendations.get(name, {}).get("recommendation", {}).get("recommendation")
                summary = recommendations.get(name, {}).get("recommendation", {}).get("summary", {})
                pass_rate = summary.get("pass_rate")
                bullet = f"- **{name}**: mean {mean:.2f}" if mean is not None else f"- **{name}**"
                if pass_rate is not None:
                    bullet += f", pass rate {pass_rate:.0%}"
                if recommendation:
                    bullet += f". {recommendation}"
                lines.append(bullet)
        (consolidated / "executive_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _generate_excel_report(
        self,
        consolidated: Path,
        comparative: dict[str, Any],
        recommendations: dict[str, Any],
    ) -> None:
        try:
            import pandas as pd
        except ImportError:  # pragma: no cover - optional dependency
            logger.info("Skipping Excel report generation (pandas not available)")
            return

        summary_rows = []
        baseline_mean = _safe_get(comparative.get("baseline_stats"), ("overall", "mean"))
        summary_rows.append(
            {
                "experiment": self.baseline_name or "baseline",
                "mean": baseline_mean,
                "type": "baseline",
            }
        )
        for name, payload in comparative.get("variants", {}).items():
            summary_rows.append(
                {
                    "experiment": name,
                    "mean": _safe_get(payload.get("stats"), ("overall", "mean")),
                    "pass_rate": _safe_get(payload.get("stats"), ("overall", "pass_rate")),
                    "type": "variant",
                }
            )

        summary_df = pd.DataFrame(summary_rows)
        comparisons_df = _comparisons_dataframe(comparative, pd)
        recommendation_rows = []
        for name, payload in recommendations.items():
            rec = payload.get("recommendation", {})
            recommendation_rows.append(
                {
                    "experiment": name,
                    "recommendation": rec.get("recommendation"),
                    "best_criteria": rec.get("best_criteria"),
                }
            )
        recommendations_df = pd.DataFrame(recommendation_rows)

        excel_path = consolidated / "analysis.xlsx"
        try:
            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                summary_df.to_excel(writer, sheet_name="Summary", index=False)
                comparisons_df.to_excel(writer, sheet_name="Comparisons", index=False)
                recommendations_df.to_excel(writer, sheet_name="Recommendations", index=False)
        except ImportError:  # pragma: no cover - optional dependency
            logger.info("Skipping Excel report generation (openpyxl not available)")

    def _generate_visualizations(self, consolidated: Path, comparative: dict[str, Any]) -> None:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:  # pragma: no cover - optional dependency
            logger.info("Skipping visualizations (matplotlib not available)")
            return

        names = []
        means = []
        errors = []

        if self.baseline_name:
            names.append(self.baseline_name)
            baseline_stats = comparative.get("baseline_stats") or {}
            means.append(_safe_get(baseline_stats, ("overall", "mean")) or 0.0)
            errors.append(_safe_get(baseline_stats, ("overall", "std")) or 0.0)

        for name, payload in comparative.get("variants", {}).items():
            names.append(name)
            stats = payload.get("stats") or {}
            means.append(_safe_get(stats, ("overall", "mean")) or 0.0)
            errors.append(_safe_get(stats, ("overall", "std")) or 0.0)

        if not names:
            logger.info("Skipping visualization; no experiments available.")
            return

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(names, means, yerr=errors, capsize=5)
        ax.set_ylabel("Mean score")
        ax.set_title("Experiment Mean Scores")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        plt.xticks(rotation=30, ha="right")
        fig.tight_layout()
        fig.savefig(consolidated / "analysis_summary.png", dpi=150)
        plt.close(fig)

    # ------------------------------------------------------------------ helpers

    def _summaries_from_payload(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            return {}
        aggregates = payload.get("aggregates")
        if not isinstance(aggregates, Mapping):
            return {}
        stats = aggregates.get("score_stats")
        if not isinstance(stats, Mapping):
            return {}
        return dict(stats)

    @staticmethod
    def _config_dict(config: ExperimentConfig | None) -> dict[str, Any]:
        if not isinstance(config, ExperimentConfig):
            return {}
        return config.to_export_dict()


def _comparisons_dataframe(comparative: dict[str, Any], pd):
    rows = []
    for name, payload in comparative.get("variants", {}).items():
        comparisons = payload.get("comparisons") or {}
        if not comparisons:
            continue
        for plugin_name, diff in comparisons.items():
            if isinstance(diff, Mapping):
                for metric, value in diff.items():
                    rows.append(
                        {
                            "experiment": name,
                            "plugin": plugin_name,
                            "metric": metric,
                            "delta": value,
                        }
                    )
            else:
                rows.append(
                    {
                        "experiment": name,
                        "plugin": plugin_name,
                        "metric": "value",
                        "delta": diff,
                    }
                )
    return pd.DataFrame(rows)


def _safe_get(payload: Mapping[str, Any] | None, path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


__all__ = ["SuiteReportGenerator"]
