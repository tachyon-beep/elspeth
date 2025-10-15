"""Base class for visual analytics sinks with shared validation and rendering."""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Sequence

from elspeth.core.protocols import Artifact, ResultSink
from elspeth.core.security import normalize_determinism_level, normalize_security_level

logger = logging.getLogger(__name__)


class BaseVisualSink(ResultSink):
    """Base class for visual analytics sinks with shared validation and rendering.

    Provides common functionality for sinks that generate visual analytics artifacts:
    - Plot module loading (matplotlib, seaborn)
    - Format validation (PNG, HTML)
    - Parameter validation (DPI, figure size, on_error)
    - Artifact creation
    - Figure saving to multiple formats

    Subclasses implement:
    - write(): Generate and save visualizations
    - produces(): Declare produced artifacts
    - consumes(): Declare consumed artifacts (usually [])
    - collect_artifacts(): Return artifacts created by write()
    """

    def __init__(
        self,
        *,
        base_path: str,
        file_stem: str,
        formats: Sequence[str] | None = None,
        dpi: int = 150,
        figure_size: Sequence[float] | None = None,
        default_figure_size: tuple[float, float] = (10.0, 6.0),
        seaborn_style: str | None = "darkgrid",
        on_error: str = "abort",
        **kwargs: Any,
    ):
        """Initialize base visual sink.

        Args:
            base_path: Directory for output files
            file_stem: Base filename (without extension)
            formats: Output formats ("png", "html")
            dpi: Image resolution (dots per inch)
            figure_size: Custom figure size (width, height) in inches
            default_figure_size: Default figure size if not specified
            seaborn_style: Seaborn theme style
            on_error: Error handling strategy ("abort" or "skip")
            **kwargs: Additional arguments for subclasses
        """
        self.base_path = Path(base_path)
        self.file_stem = file_stem
        self.formats = self._validate_formats(formats or ["png"])
        self.dpi = self._validate_dpi(dpi)
        self.figure_size = self._validate_figure_size(figure_size, default_figure_size)
        self.on_error = self._validate_on_error(on_error)
        self.seaborn_style = seaborn_style

        # State tracking
        self._plot_modules: tuple[Any, Any, Any] | None = None
        self._security_level: str | None = None
        self._determinism_level: str | None = None
        self._last_written_files: list[tuple[Any, Path, dict[str, Any]]] = []

    # Validation methods ------------------------------------------------------

    @staticmethod
    def _validate_formats(formats: Sequence[str]) -> list[str]:
        """Validate and normalize format list.

        Args:
            formats: List of requested formats

        Returns:
            Normalized format list (only "png" and "html" allowed)
        """
        selected: list[str] = []
        for fmt in formats:
            normalized = (fmt or "").strip().lower()
            if normalized in {"png", "html"}:
                selected.append(normalized)
        return selected or ["png"]

    @staticmethod
    def _validate_dpi(dpi: int) -> int:
        """Validate DPI value.

        Args:
            dpi: Dots per inch

        Returns:
            Validated DPI

        Raises:
            ValueError: If DPI is not positive
        """
        if dpi <= 0:
            raise ValueError("dpi must be a positive integer")
        return int(dpi)

    @staticmethod
    def _validate_figure_size(
        figure_size: Sequence[float] | None, default: tuple[float, float]
    ) -> tuple[float, float]:
        """Validate figure size or return default.

        Args:
            figure_size: Requested figure size (width, height)
            default: Default size to use if not specified

        Returns:
            Validated figure size tuple

        Raises:
            ValueError: If figure size is invalid
        """
        if figure_size:
            if len(figure_size) != 2:
                raise ValueError("figure_size must contain exactly two numeric values")
            width, height = figure_size
            if width <= 0 or height <= 0:
                raise ValueError("figure_size values must be positive numbers")
            return (float(width), float(height))
        return default

    @staticmethod
    def _validate_on_error(on_error: str) -> str:
        """Validate on_error strategy.

        Args:
            on_error: Error handling strategy

        Returns:
            Validated strategy

        Raises:
            ValueError: If strategy is not "abort" or "skip"
        """
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        return on_error

    # Plot module loading -----------------------------------------------------

    def _load_plot_modules(self) -> tuple[Any, Any, Any]:
        """Load matplotlib and seaborn modules (cached).

        Returns:
            Tuple of (matplotlib, plt, seaborn or None)

        Raises:
            RuntimeError: If matplotlib cannot be imported
        """
        if self._plot_modules is not None:
            return self._plot_modules

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError("matplotlib is required for visual analytics") from exc

        try:
            import seaborn
        except Exception:
            seaborn = None

        self._plot_modules = (matplotlib, plt, seaborn)
        return self._plot_modules

    # Figure saving -----------------------------------------------------------

    def _save_figure_to_formats(
        self, fig: Any, plt: Any, base_name: str, extra_metadata: dict[str, Any]
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        """Save figure to all configured formats.

        Args:
            fig: Matplotlib figure object
            plt: Matplotlib pyplot module
            base_name: Base filename (without extension)
            extra_metadata: Additional metadata to attach to artifacts

        Returns:
            List of (artifact_name, path, metadata) tuples
        """
        # Generate PNG bytes
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=self.dpi)
        plt.close(fig)
        png_bytes = buffer.getvalue()

        written: list[tuple[str, Path, dict[str, Any]]] = []

        # Save PNG if requested
        if "png" in self.formats:
            png_path = self.base_path / f"{base_name}.png"
            png_path.write_bytes(png_bytes)
            written.append((f"{base_name}_png", png_path, extra_metadata))

        # Save HTML if requested
        if "html" in self.formats:
            encoded = base64.b64encode(png_bytes).decode("ascii")
            html_path = self.base_path / f"{base_name}.html"
            html_content = self._render_html_wrapper(encoded, base_name, extra_metadata)
            html_path.write_text(html_content, encoding="utf-8")
            written.append((f"{base_name}_html", html_path, extra_metadata))

        return written

    def _render_html_wrapper(
        self, encoded_png: str, title: str, metadata: dict[str, Any]
    ) -> str:
        """Render basic HTML wrapper. Override for custom layouts.

        Args:
            encoded_png: Base64-encoded PNG image
            title: Chart title
            metadata: Additional metadata (ignored in base implementation)

        Returns:
            HTML string
        """
        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
      img {{ max-width: 100%; height: auto; }}
    </style>
  </head>
  <body>
    <h1>{title}</h1>
    <img src="data:image/png;base64,{encoded_png}" alt="{title}" />
  </body>
</html>
"""

    # Artifact creation -------------------------------------------------------

    def _create_artifact_from_file(self, path: Path, metadata: dict[str, Any]) -> Artifact:
        """Create artifact from file path.

        Args:
            path: Path to artifact file
            metadata: Additional metadata

        Returns:
            Artifact object with security context
        """
        suffix = path.suffix.lower()
        if suffix == ".png":
            content_type = "image/png"
        elif suffix == ".html":
            content_type = "text/html"
        else:
            content_type = "application/octet-stream"

        artifact_metadata = {"path": str(path), "content_type": content_type}
        artifact_metadata.update(metadata)

        return Artifact(
            id="",
            type=content_type,
            path=str(path),
            metadata=artifact_metadata,
            persist=True,
            security_level=self._security_level,
            determinism_level=self._determinism_level,
        )

    def _update_security_context_from_metadata(self, metadata: dict[str, Any] | None) -> None:
        """Update security context from result metadata.

        Args:
            metadata: Result metadata containing security_level and determinism_level
        """
        if metadata:
            self._security_level = normalize_security_level(metadata.get("security_level"))
            self._determinism_level = normalize_determinism_level(metadata.get("determinism_level"))
        else:
            self._security_level = None
            self._determinism_level = None

    # Abstract methods (must be implemented by subclasses) -------------------

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Generate and save visualizations. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement write()")

    def produces(self):
        """Declare produced artifacts. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement produces()")

    def consumes(self):
        """Declare consumed artifacts. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement consumes()")

    def collect_artifacts(self):
        """Return artifacts created by write(). Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement collect_artifacts()")


__all__ = ["BaseVisualSink"]
