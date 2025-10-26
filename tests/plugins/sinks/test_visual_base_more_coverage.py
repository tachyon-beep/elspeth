from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from elspeth.plugins.nodes.sinks._visual_base import BaseVisualSink


def test_visual_base_validation_and_save(tmp_path: Path):
    sink = BaseVisualSink(
        base_path=str(tmp_path),
        file_stem="viz",
        formats=["png", "html"],
        dpi=100,
        figure_size=(2, 1),
        allow_downgrade=True,
    )
    # Load plotting backends and create a simple figure
    _, pyplot, _ = sink._load_plot_modules()
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    written = sink._save_figure_to_formats(fig, pyplot, "chart", {"note": "ok"})
    # Both png and html should be produced
    names = {name for name, _, _ in written}
    assert names == {"chart_png", "chart_html"}
    assert (tmp_path / "chart.png").exists()
    assert (tmp_path / "chart.html").exists()
    # HTML wrapper should contain title
    html_text = (tmp_path / "chart.html").read_text(encoding="utf-8")
    assert "<h1>chart</h1>" in html_text


def test_visual_base_update_security_context():
    sink = BaseVisualSink(base_path=".", file_stem="x", allow_downgrade=True)
    sink._update_security_context_from_metadata({"security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    # Access internal attributes to confirm set
    assert sink._artifact_security_level.name == "OFFICIAL"
    assert sink._artifact_determinism_level.name == "GUARANTEED"
    # Reset to None when metadata absent
    sink._update_security_context_from_metadata(None)
    assert sink._artifact_security_level is None
    assert sink._artifact_determinism_level is None


def test_visual_base_invalid_params():
    # Invalid DPI
    with pytest.raises(ValueError):
        BaseVisualSink(base_path=".", file_stem="x", dpi=0, allow_downgrade=True)
    # Invalid figure size
    with pytest.raises(ValueError):
        BaseVisualSink(base_path=".", file_stem="x", figure_size=(0, 1), allow_downgrade=True)
    with pytest.raises(ValueError):
        BaseVisualSink(base_path=".", file_stem="x", figure_size=(1,), allow_downgrade=True)  # type: ignore[arg-type]
    # Invalid on_error
    with pytest.raises(ValueError):
        BaseVisualSink(base_path=".", file_stem="x", on_error="noop", allow_downgrade=True)
