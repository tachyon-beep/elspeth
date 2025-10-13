"""Tests for enhanced visual analytics sink."""

from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.plugins.outputs.enhanced_visual_report import EnhancedVisualAnalyticsSink

pytest.importorskip("matplotlib")  # Skip entire module if matplotlib is unavailable


def _sample_payload_with_scores() -> dict:
    """Create a sample payload with individual row scores."""
    return {
        "results": [
            {"metrics": {"scores": {"analysis": 4.2, "safety": 3.8}}},
            {"metrics": {"scores": {"analysis": 3.9, "safety": 4.5}}},
            {"metrics": {"scores": {"analysis": 4.8, "safety": 3.2}}},
            {"metrics": {"scores": {"analysis": 3.5, "safety": 4.1}}},
            {"metrics": {"scores": {"analysis": 4.1, "safety": 3.9}}},
        ]
    }


def _sample_payload_with_effect_sizes() -> dict:
    """Create a sample payload with baseline comparison and effect sizes."""
    return {
        "results": [
            {"metrics": {"scores": {"analysis": 4.2, "safety": 3.8}}},
            {"metrics": {"scores": {"analysis": 3.9, "safety": 4.5}}},
            {"metrics": {"scores": {"analysis": 4.8, "safety": 3.2}}},
        ],
        "baseline_comparison": {
            "score_significance": {
                "analysis": {
                    "effect_size": 0.42,
                    "p_value": 0.03,
                    "baseline_mean": 3.5,
                    "variant_mean": 4.1,
                },
                "safety": {
                    "effect_size": -0.28,
                    "p_value": 0.15,
                    "baseline_mean": 4.2,
                    "variant_mean": 3.9,
                },
            }
        },
    }


def test_enhanced_visual_sink_creates_violin_plot(tmp_path: Path) -> None:
    """Test that violin plot is generated with score distributions."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_violin",
        formats=["png"],
        chart_types=["violin"],
        dpi=120,
    )
    payload = _sample_payload_with_scores()
    metadata = {
        "security_level": "OFFICIAL",
        "determinism_level": "guaranteed",
    }

    sink.write(payload, metadata=metadata)
    artifacts = sink.collect_artifacts()

    assert (tmp_path / "test_violin_violin.png").exists()
    assert "enhanced_visual_violin_png" in artifacts
    artifact = artifacts["enhanced_visual_violin_png"]
    assert artifact.metadata["chart_type"] == "violin"
    assert artifact.security_level == "OFFICIAL"
    assert artifact.determinism_level == "guaranteed"


def test_enhanced_visual_sink_creates_box_plot(tmp_path: Path) -> None:
    """Test that box plot is generated with quartile information."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_box",
        formats=["png"],
        chart_types=["box"],
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    assert (tmp_path / "test_box_box.png").exists()
    assert "enhanced_visual_box_png" in artifacts
    assert artifacts["enhanced_visual_box_png"].metadata["chart_type"] == "box"


def test_enhanced_visual_sink_creates_heatmap(tmp_path: Path) -> None:
    """Test that heatmap is generated for multi-criteria correlation."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_heatmap",
        formats=["png"],
        chart_types=["heatmap"],
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    assert (tmp_path / "test_heatmap_heatmap.png").exists()
    assert "enhanced_visual_heatmap_png" in artifacts
    assert artifacts["enhanced_visual_heatmap_png"].metadata["chart_type"] == "heatmap"


def test_enhanced_visual_sink_creates_forest_plot(tmp_path: Path) -> None:
    """Test that forest plot is generated with effect sizes."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_forest",
        formats=["png"],
        chart_types=["forest"],
    )
    payload = _sample_payload_with_effect_sizes()

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    assert (tmp_path / "test_forest_forest.png").exists()
    assert "enhanced_visual_forest_png" in artifacts
    assert artifacts["enhanced_visual_forest_png"].metadata["chart_type"] == "forest"


def test_enhanced_visual_sink_creates_distribution_overlay(tmp_path: Path) -> None:
    """Test that distribution overlay histogram is generated."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_dist",
        formats=["png"],
        chart_types=["distribution"],
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    assert (tmp_path / "test_dist_distribution.png").exists()
    assert "enhanced_visual_distribution_png" in artifacts
    assert artifacts["enhanced_visual_distribution_png"].metadata["chart_type"] == "distribution"


def test_enhanced_visual_sink_creates_multiple_chart_types(tmp_path: Path) -> None:
    """Test that multiple chart types can be generated simultaneously."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_multi",
        formats=["png", "html"],
        chart_types=["violin", "heatmap", "distribution"],
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    # Check that all chart types were generated in both formats
    assert (tmp_path / "test_multi_violin.png").exists()
    assert (tmp_path / "test_multi_violin.html").exists()
    assert (tmp_path / "test_multi_heatmap.png").exists()
    assert (tmp_path / "test_multi_heatmap.html").exists()
    assert (tmp_path / "test_multi_distribution.png").exists()
    assert (tmp_path / "test_multi_distribution.html").exists()

    # Check that all artifacts are present
    assert "enhanced_visual_violin_png" in artifacts
    assert "enhanced_visual_violin_html" in artifacts
    assert "enhanced_visual_heatmap_png" in artifacts
    assert "enhanced_visual_heatmap_html" in artifacts
    assert "enhanced_visual_distribution_png" in artifacts
    assert "enhanced_visual_distribution_html" in artifacts


def test_enhanced_visual_sink_handles_empty_payload(tmp_path: Path) -> None:
    """Test that sink handles empty payload gracefully."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        formats=["png"],
        chart_types=["violin"],
    )
    payload = {"results": []}

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    # Should not create any files
    assert not list(tmp_path.iterdir())
    assert artifacts == {}


def test_enhanced_visual_sink_handles_insufficient_data_for_heatmap(tmp_path: Path) -> None:
    """Test that heatmap is skipped when there are fewer than 2 criteria."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_single",
        formats=["png"],
        chart_types=["heatmap"],
        on_error="skip",
    )
    payload = {
        "results": [
            {"metrics": {"scores": {"analysis": 4.2}}},
            {"metrics": {"scores": {"analysis": 3.9}}},
        ]
    }

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    # Heatmap requires at least 2 criteria, should not generate file
    assert not (tmp_path / "test_single_heatmap.png").exists()
    assert artifacts == {}


def test_enhanced_visual_sink_handles_missing_effect_sizes(tmp_path: Path) -> None:
    """Test that forest plot is skipped when effect size data is missing."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_no_effects",
        formats=["png"],
        chart_types=["forest"],
        on_error="skip",
    )
    payload = _sample_payload_with_scores()  # No baseline comparison

    sink.write(payload, metadata={})
    artifacts = sink.collect_artifacts()

    # Forest plot requires effect sizes, should not generate file
    assert not (tmp_path / "test_no_effects_forest.png").exists()
    assert artifacts == {}


def test_enhanced_visual_sink_custom_figure_size(tmp_path: Path) -> None:
    """Test that custom figure size is applied."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_custom",
        formats=["png"],
        chart_types=["violin"],
        figure_size=[12.0, 8.0],
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})

    # Check file was created (actual size verification would require image analysis)
    assert (tmp_path / "test_custom_violin.png").exists()


def test_enhanced_visual_sink_custom_color_palette(tmp_path: Path) -> None:
    """Test that custom color palette is applied."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_palette",
        formats=["png"],
        chart_types=["violin"],
        color_palette="viridis",
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})

    assert (tmp_path / "test_palette_violin.png").exists()


def test_enhanced_visual_sink_validates_format(tmp_path: Path) -> None:
    """Test that invalid formats are filtered out."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        formats=["png", "invalid", "html"],
        chart_types=["violin"],
    )
    # Should filter to only valid formats
    assert set(sink.formats) == {"png", "html"}


def test_enhanced_visual_sink_validates_chart_types(tmp_path: Path) -> None:
    """Test that invalid chart types are filtered out."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        chart_types=["violin", "invalid_chart", "heatmap"],
    )
    # Should filter to only valid chart types
    assert set(sink.chart_types) == {"violin", "heatmap"}


def test_enhanced_visual_sink_validates_dpi(tmp_path: Path) -> None:
    """Test that invalid DPI raises ValueError."""
    with pytest.raises(ValueError, match="dpi must be a positive integer"):
        EnhancedVisualAnalyticsSink(
            base_path=str(tmp_path),
            dpi=-10,
        )


def test_enhanced_visual_sink_validates_figure_size(tmp_path: Path) -> None:
    """Test that invalid figure size raises ValueError."""
    with pytest.raises(ValueError, match="figure_size must contain exactly two numeric values"):
        EnhancedVisualAnalyticsSink(
            base_path=str(tmp_path),
            figure_size=[10.0],  # Only one value
        )

    with pytest.raises(ValueError, match="figure_size values must be positive numbers"):
        EnhancedVisualAnalyticsSink(
            base_path=str(tmp_path),
            figure_size=[-10.0, 5.0],  # Negative value
        )


def test_enhanced_visual_sink_validates_on_error(tmp_path: Path) -> None:
    """Test that invalid on_error mode raises ValueError."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        EnhancedVisualAnalyticsSink(
            base_path=str(tmp_path),
            on_error="invalid",
        )


def test_enhanced_visual_sink_html_output(tmp_path: Path) -> None:
    """Test that HTML files contain embedded PNG and proper structure."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="test_html",
        formats=["html"],
        chart_types=["violin"],
    )
    payload = _sample_payload_with_scores()

    sink.write(payload, metadata={})

    html_path = tmp_path / "test_html_violin.html"
    assert html_path.exists()

    html_content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content
    assert '<html lang="en">' in html_content
    assert "Violin Visualization" in html_content
    assert "data:image/png;base64," in html_content
    assert "<img src=" in html_content


def test_enhanced_visual_sink_produces_descriptors(tmp_path: Path) -> None:
    """Test that produces() returns correct artifact descriptors."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        chart_types=["violin", "heatmap"],
        formats=["png", "html"],
    )

    descriptors = sink.produces()

    # Should have 4 descriptors (2 chart types × 2 formats)
    assert len(descriptors) == 4

    descriptor_names = {d.name for d in descriptors}
    assert "enhanced_visual_violin_png" in descriptor_names
    assert "enhanced_visual_violin_html" in descriptor_names
    assert "enhanced_visual_heatmap_png" in descriptor_names
    assert "enhanced_visual_heatmap_html" in descriptor_names


def test_enhanced_visual_sink_consumes_nothing(tmp_path: Path) -> None:
    """Test that consumes() returns empty list (no dependencies)."""
    sink = EnhancedVisualAnalyticsSink(base_path=str(tmp_path))
    assert sink.consumes() == []


def test_enhanced_visual_sink_on_error_skip_backend_failure(monkeypatch, tmp_path: Path) -> None:
    """Test that on_error=skip handles backend initialization failure."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        on_error="skip",
    )

    def _fail():
        raise RuntimeError("matplotlib missing")

    monkeypatch.setattr(sink, "_load_plot_modules", _fail)
    payload = _sample_payload_with_scores()

    # Should not raise, should skip silently
    sink.write(payload, metadata={})
    assert not list(tmp_path.iterdir())
    assert sink.collect_artifacts() == {}


def test_enhanced_visual_sink_on_error_skip_chart_generation_failure(monkeypatch, tmp_path: Path) -> None:
    """Test that on_error=skip handles individual chart generation failures."""
    sink = EnhancedVisualAnalyticsSink(
        base_path=str(tmp_path),
        chart_types=["violin", "heatmap"],
        on_error="skip",
    )

    original_generate = sink._generate_violin_plot

    def _fail_violin(*args, **kwargs):
        raise RuntimeError("Violin plot failed")

    monkeypatch.setattr(sink, "_generate_violin_plot", _fail_violin)
    payload = _sample_payload_with_scores()

    # Should skip violin but still generate heatmap
    sink.write(payload, metadata={})

    assert not (tmp_path / f"{sink.file_stem}_violin.png").exists()
    # Heatmap should still be generated
    assert (tmp_path / f"{sink.file_stem}_heatmap.png").exists()
