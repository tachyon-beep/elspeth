import builtins
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from elspeth.core.experiments.config import ExperimentSuite
from elspeth.tools.reporting import SuiteReportGenerator


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
            "row_plugins": [{"name": "score_extractor", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
            "aggregator_plugins": [{"name": "score_stats", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
            "baseline_plugins": [{"name": "score_delta", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
            "llm_middlewares": [{"name": "audit_logger", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
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


def test_suite_report_excel_generation_with_stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite = _write_suite(tmp_path / "suite")
    results = {
        "baseline": {"payload": _basic_payload(3.0), "config": suite.baseline},
        "variant": {
            "payload": _basic_payload(3.2),
            "config": next(exp for exp in suite.experiments if exp.name == "variant"),
            "baseline_comparison": {"score_delta": {"quality": 0.2}},
        },
    }
    reporter = SuiteReportGenerator(suite, results)

    class FakeDataFrame:
        def __init__(self, rows):
            self.rows = rows

        def to_excel(self, writer, sheet_name, index=False):
            writer.register(sheet_name, self.rows)

    class FakeExcelWriter:
        def __init__(self, path, engine=None):
            self.path = Path(path)
            self.records = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.path.write_text(json.dumps(self.records, indent=2, sort_keys=True), encoding="utf-8")

        def register(self, sheet_name, rows):
            self.records[sheet_name] = rows

    fake_pd = types.ModuleType("pandas")
    fake_pd.ExcelWriter = FakeExcelWriter

    def _dataframe(data):
        return FakeDataFrame(data)

    fake_pd.DataFrame = _dataframe
    monkeypatch.setitem(sys.modules, "pandas", fake_pd)
    monkeypatch.setitem(sys.modules, "openpyxl", types.ModuleType("openpyxl"))

    consolidated = tmp_path / "reports" / "consolidated"
    consolidated.mkdir(parents=True, exist_ok=True)
    comparative = reporter._generate_comparative(consolidated)
    recommendations = reporter._generate_recommendations(consolidated)
    reporter._generate_excel_report(consolidated, comparative, recommendations)

    excel_path = consolidated / "analysis.xlsx"
    data = json.loads(excel_path.read_text(encoding="utf-8"))
    assert "Summary" in data
    assert "Comparisons" in data
    assert "Recommendations" in data


def test_suite_report_visualization_generation_with_stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite = _write_suite(tmp_path / "suite")
    results = {
        "baseline": {"payload": _basic_payload(2.0), "config": suite.baseline},
        "variant": {"payload": _basic_payload(3.0), "config": next(exp for exp in suite.experiments if exp.name == "variant")},
    }
    reporter = SuiteReportGenerator(suite, results)
    consolidated = tmp_path / "reports" / "consolidated"
    consolidated.mkdir(parents=True, exist_ok=True)
    comparative = reporter._generate_comparative(consolidated)

    class FakeFigure:
        def __init__(self):
            self.saved = None

        def tight_layout(self):
            pass

        def savefig(self, path, dpi=150):
            self.saved = path
            Path(path).write_text("figure", encoding="utf-8")

    class FakeAxes:
        def bar(self, *args, **kwargs):
            pass

        def set_ylabel(self, *args, **kwargs):
            pass

        def set_title(self, *args, **kwargs):
            pass

        def grid(self, *args, **kwargs):
            pass

    class FakePlt:
        def __init__(self):
            self.fig = FakeFigure()

        def subplots(self, figsize=(8, 4)):
            return self.fig, FakeAxes()

        def xticks(self, *args, **kwargs):
            pass

        def close(self, fig):
            pass

    fake_matplotlib = types.ModuleType("matplotlib")
    fake_matplotlib.use = lambda backend: None  # type: ignore[attr-defined]
    fake_plt = FakePlt()
    monkeypatch.setitem(sys.modules, "matplotlib", fake_matplotlib)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", fake_plt)

    reporter._generate_visualizations(consolidated, comparative)
    assert (consolidated / "analysis_summary.png").exists()
