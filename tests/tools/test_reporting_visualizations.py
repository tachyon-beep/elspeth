from types import SimpleNamespace
from pathlib import Path

from elspeth.tools.reporting import SuiteReportGenerator


def test_generate_visualizations_skips_when_no_experiments(tmp_path: Path):
    # Build minimal suite stub with no baseline
    suite = SimpleNamespace(baseline=None)
    gen = SuiteReportGenerator(suite=suite, results={})
    out = tmp_path
    gen._generate_visualizations(out, {"variants": {}})
    assert not (out / "analysis_summary.png").exists()
