import json


def test_analytics_report_sink_writes(tmp_path):
    from elspeth.plugins.outputs.analytics_report import AnalyticsReportSink

    sink = AnalyticsReportSink(base_path=tmp_path / "reports", file_stem="summary")

    payload = {
        "results": [{"row": {"APPID": "1"}, "metrics": {"score": 0.8}}],
        "failures": [],
        "aggregates": {"score_stats": {"criteria": {"crit": {"mean": 0.8}}, "overall": {"mean": 0.8}}},
        "baseline_comparison": {"score_significance": {"crit": {"p_value": 0.04}}},
        "score_cliffs_delta": {"crit": {"delta": 0.6}},
        "metadata": {"early_stop": {"metric": "scores.analysis"}},
    }
    sink.write(payload, metadata={"security_level": "official"})

    json_path = tmp_path / "reports" / "summary.json"
    md_path = tmp_path / "reports" / "summary.md"
    assert json_path.exists() and md_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["rows"] == 1
    assert data["aggregates"]["score_stats"]["overall"]["mean"] == 0.8
    assert data["baseline_comparison"]["score_significance"]["crit"]["p_value"] == 0.04
    assert "score_cliffs_delta" in data["analytics"]


def test_analytics_report_sink_skip_on_error(tmp_path, monkeypatch):
    from elspeth.plugins.outputs.analytics_report import AnalyticsReportSink

    sink = AnalyticsReportSink(base_path=tmp_path / "reports", on_error="skip")

    def faulty_write(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr("pathlib.Path.write_text", faulty_write)

    sink.write({"results": []})
    # Should not raise even though write_text failed
