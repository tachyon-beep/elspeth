from pathlib import Path

from scripts import plugin_scaffold


def test_scaffold_creates_row_plugin(tmp_path):
    exit_code = plugin_scaffold.main(
        [
            "row",
            "sample_metric",
            "--directory",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    created = tmp_path / "sample_metric.py"
    assert created.exists()
    content = created.read_text(encoding="utf-8")
    assert "class SampleMetric" in content
    assert "register_row_plugin" in content


def test_scaffold_respects_force(tmp_path):
    destination = tmp_path / "example.py"
    destination.write_text("existing", encoding="utf-8")

    exit_code = plugin_scaffold.main(
        [
            "baseline",
            "example",
            "--directory",
            str(tmp_path),
        ]
    )
    assert exit_code == 1

    exit_code = plugin_scaffold.main(
        [
            "baseline",
            "example",
            "--directory",
            str(tmp_path),
            "--force",
        ]
    )
    assert exit_code == 0
    assert "class Example" in destination.read_text(encoding="utf-8")
