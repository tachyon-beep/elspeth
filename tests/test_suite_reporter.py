import builtins
import importlib.util
import json
from pathlib import Path

import pytest

from dmp.core.experiments.config import ExperimentSuite
from dmp.tools.reporting import SuiteReportGenerator


def _basic_payload(mean: float) -> dict:
    stats = {
        "overall": {
            "count": 1,
            "mean": mean,
            "std": 0.0,
            "pass_rate": 1.0,
        },
        "criteria": {
            "quality": {
                "count": 1,
                "mean": mean,
                "std": 0.0,
                "pass_rate": 1.0,
            }
        },
    }
    return {
        "results": [{"metrics": {"scores": {"quality": mean}}}],
        "aggregates": {
            "score_stats": stats,
            "score_recommendation": {
                "recommendation": "Strong performance",
                "summary": stats["overall"],
                "best_criteria": "quality",
            },
        },
        "failures": [],
    }


def _write_suite(tmp_path: Path) -> ExperimentSuite:
    for name, is_baseline in (("baseline", True), ("variant", False)):
        folder = tmp_path / name
        folder.mkdir(parents=True, exist_ok=True)
        config = {
            "name": name,
            "temperature": 0.5,
            "max_tokens": 128,
            "enabled": True,
            "is_baseline": is_baseline,
            "criteria": [{"name": "quality"}],
            "row_plugins": [{"name": "score_extractor"}],
            "aggregator_plugins": [{"name": "score_stats"}],
            "baseline_plugins": [{"name": "score_delta"}],
            "llm_middlewares": [{"name": "audit_logger"}],
        }
        (folder / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (folder / "system_prompt.md").write_text("system", encoding="utf-8")
        (folder / "user_prompt.md").write_text("user", encoding="utf-8")
    return ExperimentSuite.load(tmp_path)


def test_suite_report_generator_creates_core_outputs(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path / "suite")
    baseline_payload = _basic_payload(3.0)
    variant_payload = _basic_payload(3.5)
    results = {
        "baseline": {"payload": baseline_payload, "config": suite.baseline},
        "variant": {
            "payload": variant_payload,
            "config": next(exp for exp in suite.experiments if exp.name == "variant"),
            "baseline_comparison": {"score_delta": {"quality": 0.5}},
        },
    }

    reporter = SuiteReportGenerator(suite, results)
    reporter.generate_all_reports(tmp_path / "reports")

    consolidated = tmp_path / "reports" / "consolidated"
    assert (consolidated / "validation_results.json").exists()
    assert (consolidated / "comparative_analysis.json").exists()
    assert (consolidated / "recommendations.json").exists()
    assert (consolidated / "analysis_config.json").exists()
    assert (consolidated / "executive_summary.md").exists()

    baseline_stats = json.loads((tmp_path / "reports" / "baseline" / "stats.json").read_text(encoding="utf-8"))
    assert baseline_stats["row_count"] == 1
    analysis_config = json.loads((consolidated / "analysis_config.json").read_text(encoding="utf-8"))
    assert analysis_config["plugin_summary"]["row_plugins"] == ["score_extractor"]

    if importlib.util.find_spec("pandas") and importlib.util.find_spec("openpyxl"):
        assert (consolidated / "analysis.xlsx").exists()

    if importlib.util.find_spec("matplotlib"):
        assert (consolidated / "analysis_summary.png").exists()


def test_suite_report_generator_handles_missing_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite = _write_suite(tmp_path / "suite")
    results = {
        "baseline": {"payload": _basic_payload(3.0), "config": suite.baseline},
    }
    reporter = SuiteReportGenerator(suite, results)

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"pandas", "matplotlib", "matplotlib.pyplot"}:
            raise ImportError("simulated missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    target = tmp_path / "no_deps"
    reporter.generate_all_reports(target)
    consolidated = target / "consolidated"
    assert not (consolidated / "analysis.xlsx").exists()
    assert not (consolidated / "analysis_summary.png").exists()


def test_suite_report_generator_failure_analysis(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path / "suite")
    failure_payload = _basic_payload(2.5)
    failure_payload["failures"] = [{"row": {"APPID": "1"}, "error": "boom"}]
    results = {
        "baseline": {"payload": _basic_payload(3.0), "config": suite.baseline},
        "variant": {
            "payload": failure_payload,
            "config": next(exp for exp in suite.experiments if exp.name == "variant"),
            "baseline_comparison": {"score_delta": {"quality": -0.5}},
        },
    }
    SuiteReportGenerator(suite, results).generate_all_reports(tmp_path / "reports")
    consolidated = tmp_path / "reports" / "consolidated"
    failure_data = json.loads((consolidated / "failure_analysis.json").read_text(encoding="utf-8"))
    assert "variant" in failure_data
    exec_summary = (consolidated / "executive_summary.md").read_text(encoding="utf-8")
    assert "variant" in exec_summary
