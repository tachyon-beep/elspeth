"""Coverage tests for _visual_base to reach 80% coverage.

Focuses on uncovered lines:
- Line 167: Cached plot modules
- Lines 190-211: _save_figure_to_formats
- Lines 225-227: HTML wrapper rendering
- Lines 256-267: Artifact creation with different content types
- Lines 294, 298, 302, 306: Abstract methods
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from elspeth.plugins.nodes.sinks._visual_base import BaseVisualSink


class ConcreteVisualSink(BaseVisualSink):
    """Concrete implementation for testing."""

    def __init__(self, **kwargs):
        super().__init__(
            base_path=kwargs.get("base_path", "/tmp/test"),
            file_stem=kwargs.get("file_stem", "test"),
            formats=kwargs.get("formats"),
            dpi=kwargs.get("dpi", 150),
            figure_size=kwargs.get("figure_size"),
            on_error=kwargs.get("on_error", "abort"),
        )
        self._artifacts = {}

    def write(self, results, *, metadata=None):
        """Concrete implementation."""
        self._update_security_context_from_metadata(metadata)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Load plot modules
        matplotlib, plt, sns = self._load_plot_modules()

        # Create a simple figure
        fig, ax = plt.subplots(figsize=self.figure_size)
        ax.plot([1, 2, 3], [1, 4, 9])
        ax.set_title("Test Plot")

        # Save to formats
        extra_metadata = {"type": "test_visual"}
        self._last_written_files = self._save_figure_to_formats(
            fig, plt, self.file_stem, extra_metadata
        )

        # Create artifacts
        for artifact_name, path, meta in self._last_written_files:
            self._artifacts[artifact_name] = self._create_artifact_from_file(path, meta)

    def produces(self):
        """Concrete implementation."""
        return []

    def consumes(self):
        """Concrete implementation."""
        return []

    def collect_artifacts(self):
        """Concrete implementation."""
        return self._artifacts


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create temporary output directory."""
    output_dir = tmp_path / "visual_outputs"
    output_dir.mkdir()
    return output_dir


def test_validate_formats():
    """Test format validation."""
    # Valid formats
    assert BaseVisualSink._validate_formats(["png"]) == ["png"]
    assert BaseVisualSink._validate_formats(["html"]) == ["html"]
    assert BaseVisualSink._validate_formats(["png", "html"]) == ["png", "html"]

    # Invalid formats filtered out
    assert BaseVisualSink._validate_formats(["png", "pdf", "html"]) == ["png", "html"]
    assert BaseVisualSink._validate_formats(["svg", "pdf"]) == ["png"]  # Default to png

    # Case insensitive
    assert BaseVisualSink._validate_formats(["PNG", "HTML"]) == ["png", "html"]


def test_validate_dpi():
    """Test DPI validation."""
    assert BaseVisualSink._validate_dpi(150) == 150
    assert BaseVisualSink._validate_dpi(300) == 300

    with pytest.raises(ValueError, match="must be a positive integer"):
        BaseVisualSink._validate_dpi(0)

    with pytest.raises(ValueError, match="must be a positive integer"):
        BaseVisualSink._validate_dpi(-100)


def test_validate_figure_size():
    """Test figure size validation."""
    # Valid size
    assert BaseVisualSink._validate_figure_size([10, 6], (8, 5)) == (10.0, 6.0)

    # None uses default
    assert BaseVisualSink._validate_figure_size(None, (8, 5)) == (8, 5)

    # Wrong number of values
    with pytest.raises(ValueError, match="exactly two numeric values"):
        BaseVisualSink._validate_figure_size([10], (8, 5))

    with pytest.raises(ValueError, match="exactly two numeric values"):
        BaseVisualSink._validate_figure_size([10, 6, 4], (8, 5))

    # Non-positive values
    with pytest.raises(ValueError, match="must be positive"):
        BaseVisualSink._validate_figure_size([0, 6], (8, 5))

    with pytest.raises(ValueError, match="must be positive"):
        BaseVisualSink._validate_figure_size([10, -6], (8, 5))


def test_validate_on_error():
    """Test on_error validation."""
    assert BaseVisualSink._validate_on_error("abort") == "abort"
    assert BaseVisualSink._validate_on_error("skip") == "skip"

    with pytest.raises(ValueError, match="must be 'abort' or 'skip'"):
        BaseVisualSink._validate_on_error("invalid")


def test_load_plot_modules_cached(temp_output_dir):
    """Test plot modules are cached after first load - line 167."""
    sink = ConcreteVisualSink(base_path=str(temp_output_dir))

    # First load
    modules1 = sink._load_plot_modules()
    assert modules1 is not None
    assert len(modules1) == 3

    # Second load should return cached
    modules2 = sink._load_plot_modules()
    assert modules2 is modules1  # Same object


def test_save_figure_to_png_only(temp_output_dir):
    """Test saving figure to PNG only - lines 190-211."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        file_stem="test_png",
        formats=["png"]
    )

    results = {"results": []}
    sink.write(results, metadata={"experiment": "test"})

    # Check PNG was created
    png_path = temp_output_dir / "test_png.png"
    assert png_path.exists()

    # Check HTML was NOT created
    html_path = temp_output_dir / "test_png.html"
    assert not html_path.exists()

    # Check written files tracking
    assert len(sink._last_written_files) == 1
    assert sink._last_written_files[0][0] == "test_png_png"


def test_save_figure_to_html_only(temp_output_dir):
    """Test saving figure to HTML only - lines 190-211."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        file_stem="test_html",
        formats=["html"]
    )

    results = {"results": []}
    sink.write(results, metadata={"experiment": "test"})

    # Check HTML was created
    html_path = temp_output_dir / "test_html.html"
    assert html_path.exists()

    # Check PNG was NOT created
    png_path = temp_output_dir / "test_html.png"
    assert not png_path.exists()

    # Check written files tracking
    assert len(sink._last_written_files) == 1
    assert sink._last_written_files[0][0] == "test_html_html"


def test_save_figure_to_both_formats(temp_output_dir):
    """Test saving figure to both PNG and HTML."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        file_stem="test_both",
        formats=["png", "html"]
    )

    results = {"results": []}
    sink.write(results, metadata={"experiment": "test"})

    # Check both were created
    png_path = temp_output_dir / "test_both.png"
    html_path = temp_output_dir / "test_both.html"
    assert png_path.exists()
    assert html_path.exists()

    # Check written files tracking
    assert len(sink._last_written_files) == 2


def test_html_wrapper_rendering(temp_output_dir):
    """Test HTML wrapper rendering - lines 225-227."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        file_stem="test_html",
        formats=["html"]
    )

    results = {"results": []}
    sink.write(results, metadata={"experiment": "test"})

    # Read and check HTML content
    html_path = temp_output_dir / "test_html.html"
    html_content = html_path.read_text()

    # Check structure
    assert "<!DOCTYPE html>" in html_content
    assert "<html lang=\"en\">" in html_content
    assert "<title>test_html</title>" in html_content
    assert "<h1>test_html</h1>" in html_content
    assert "data:image/png;base64," in html_content
    assert '<img src="data:image/png;base64,' in html_content


def test_html_escaping_in_title(temp_output_dir):
    """Test HTML escaping in title to prevent injection."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        file_stem="<script>alert('xss')</script>",
        formats=["html"]
    )

    results = {"results": []}
    sink.write(results, metadata={})

    html_path = temp_output_dir / "<script>alert('xss')</script>.html"
    html_content = html_path.read_text()

    # Script tags should be escaped
    assert "<script>" not in html_content
    assert "&lt;script&gt;" in html_content


def test_create_artifact_from_png(temp_output_dir):
    """Test artifact creation from PNG file - lines 256-267."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        formats=["png"]
    )

    sink._security_level = "internal"
    sink._determinism_level = "deterministic"

    results = {"results": []}
    sink.write(results, metadata={})

    # Check artifact
    artifacts = sink.collect_artifacts()
    assert "test_png" in artifacts

    artifact = artifacts["test_png"]
    assert artifact.type == "image/png"
    assert artifact.security_level == "internal"
    assert artifact.determinism_level == "deterministic"


def test_create_artifact_from_html(temp_output_dir):
    """Test artifact creation from HTML file - lines 256-267."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        formats=["html"]
    )

    sink._security_level = "confidential"
    sink._determinism_level = "nondeterministic"

    results = {"results": []}
    sink.write(results, metadata={})

    # Check artifact
    artifacts = sink.collect_artifacts()
    assert "test_html" in artifacts

    artifact = artifacts["test_html"]
    assert artifact.type == "text/html"
    assert artifact.security_level == "confidential"
    assert artifact.determinism_level == "nondeterministic"


def test_update_security_context_from_metadata(temp_output_dir):
    """Test security context update from metadata."""
    sink = ConcreteVisualSink(base_path=str(temp_output_dir))

    # With metadata
    metadata = {
        "security_level": "restricted",
        "determinism_level": "nondeterministic"
    }
    sink._update_security_context_from_metadata(metadata)
    assert sink._security_level == "restricted"
    assert sink._determinism_level == "nondeterministic"

    # Without metadata
    sink._update_security_context_from_metadata(None)
    assert sink._security_level is None
    assert sink._determinism_level is None


def test_abstract_methods_raise():
    """Test that abstract methods raise NotImplementedError - lines 294, 298, 302, 306."""
    sink = BaseVisualSink(
        base_path="/tmp/test",
        file_stem="test"
    )

    with pytest.raises(NotImplementedError, match="must implement write"):
        sink.write({})

    with pytest.raises(NotImplementedError, match="must implement produces"):
        sink.produces()

    with pytest.raises(NotImplementedError, match="must implement consumes"):
        sink.consumes()

    with pytest.raises(NotImplementedError, match="must implement collect_artifacts"):
        sink.collect_artifacts()


def test_custom_figure_size(temp_output_dir):
    """Test custom figure size."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        figure_size=[12, 8]
    )

    assert sink.figure_size == (12.0, 8.0)

    results = {"results": []}
    sink.write(results, metadata={})

    # Should succeed with custom size
    assert (temp_output_dir / "test.png").exists()


def test_custom_dpi(temp_output_dir):
    """Test custom DPI."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        dpi=300
    )

    assert sink.dpi == 300

    results = {"results": []}
    sink.write(results, metadata={})

    # Should succeed with custom DPI
    assert (temp_output_dir / "test.png").exists()


def test_seaborn_style_parameter(temp_output_dir):
    """Test seaborn style parameter."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        seaborn_style="whitegrid"
    )

    assert sink.seaborn_style == "whitegrid"


def test_default_values(temp_output_dir):
    """Test default values."""
    sink = ConcreteVisualSink(base_path=str(temp_output_dir))

    assert sink.formats == ["png"]
    assert sink.dpi == 150
    assert sink.figure_size == (10.0, 6.0)
    assert sink.on_error == "abort"
    assert sink.seaborn_style == "darkgrid"


def test_artifact_metadata_includes_path(temp_output_dir):
    """Test artifact metadata includes path and content type."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        formats=["png"]
    )

    results = {"results": []}
    sink.write(results, metadata={})

    artifacts = sink.collect_artifacts()
    artifact = artifacts["test_png"]

    assert "path" in artifact.metadata
    assert "content_type" in artifact.metadata
    assert artifact.metadata["content_type"] == "image/png"


def test_extra_metadata_in_artifacts(temp_output_dir):
    """Test extra metadata is included in artifacts."""
    sink = ConcreteVisualSink(
        base_path=str(temp_output_dir),
        formats=["png"]
    )

    # Write includes extra_metadata in _save_figure_to_formats
    results = {"results": []}
    sink.write(results, metadata={})

    artifacts = sink.collect_artifacts()
    artifact = artifacts["test_png"]

    # Extra metadata from write() should be in artifact
    assert "type" in artifact.metadata
    assert artifact.metadata["type"] == "test_visual"


def test_unknown_extension_uses_default_content_type(temp_output_dir):
    """Test unknown file extension uses default content type."""
    sink = ConcreteVisualSink(base_path=str(temp_output_dir))

    # Create artifact from unknown extension
    test_path = temp_output_dir / "test.unknown"
    test_path.write_text("test")

    artifact = sink._create_artifact_from_file(test_path, {})

    assert artifact.type == "application/octet-stream"
