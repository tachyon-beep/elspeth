"""Sink nodes - output vertices in the data flow graph.

Lazy loading
------------

This package exposes optional sinks that depend on third‑party libraries and
cloud SDKs (e.g., Azure SDKs, psycopg/pgvector). To keep imports lightweight and
avoid import‑time failures in environments where those optional dependencies are
not installed, this module defers importing the underlying implementation until
the first attribute access via ``__getattr__``.

Import and error behavior
-------------------------

- ``from elspeth.plugins.nodes.sinks import FooSink`` works as usual; when
  ``FooSink`` is first accessed, we import its module and return the attribute.
- If the requested name is not declared in the registry mapping, an
  ``AttributeError`` is raised (consistent with normal module semantics).
- If the target module cannot be imported (missing optional dependency), an
  ``ImportError`` is raised that includes the underlying exception to aid
  debugging (for example, missing ``azure-storage-blob``).
- If the module imports successfully but the expected attribute is missing, an
  ``ImportError`` is raised with a clear message indicating the missing symbol.

This pattern reduces the import cost in environments that only use a subset of
the sinks and keeps optional dependencies truly optional at import time.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

# Common module paths used across multiple sink mappings
_REPOSITORY_MODULE = "elspeth.plugins.nodes.sinks.repository"

__all__ = [
    "BlobResultSink",
    "AzureBlobArtifactsSink",
    "CsvResultSink",
    "LocalBundleSink",
    "ExcelResultSink",
    "ZipResultSink",
    "FileCopySink",
    "GitHubRepoSink",
    "AzureDevOpsRepoSink",
    "AzureDevOpsArtifactsRepoSink",
    "SignedArtifactSink",
    "AnalyticsReportSink",
    "VisualAnalyticsSink",
    "EnhancedVisualAnalyticsSink",
    "EmbeddingsStoreSink",
    "ReproducibilityBundleSink",
]

# Stubs for static analyzers and __all__ validation. Implementations are
# provided dynamically via __getattr__ and lazily imported on first access.
BlobResultSink: Any
AzureBlobArtifactsSink: Any
CsvResultSink: Any
LocalBundleSink: Any
ExcelResultSink: Any
ZipResultSink: Any
FileCopySink: Any
GitHubRepoSink: Any
AzureDevOpsRepoSink: Any
AzureDevOpsArtifactsRepoSink: Any
SignedArtifactSink: Any
AnalyticsReportSink: Any
VisualAnalyticsSink: Any
EnhancedVisualAnalyticsSink: Any
EmbeddingsStoreSink: Any
ReproducibilityBundleSink: Any

# isort: off
if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from elspeth.plugins.nodes.sinks.analytics_report import AnalyticsReportSink as AnalyticsReportSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.blob import AzureBlobArtifactsSink as AzureBlobArtifactsSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.blob import BlobResultSink as BlobResultSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink as CsvResultSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.embeddings_store import EmbeddingsStoreSink as EmbeddingsStoreSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.enhanced_visual_report import (
        EnhancedVisualAnalyticsSink as EnhancedVisualAnalyticsSink,  # noqa: F401
    )
    from elspeth.plugins.nodes.sinks.excel import ExcelResultSink as ExcelResultSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.file_copy import FileCopySink as FileCopySink  # noqa: F401
    from elspeth.plugins.nodes.sinks.local_bundle import LocalBundleSink as LocalBundleSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.repository import (
        AzureDevOpsArtifactsRepoSink as AzureDevOpsArtifactsRepoSink,  # noqa: F401
        AzureDevOpsRepoSink as AzureDevOpsRepoSink,  # noqa: F401
        GitHubRepoSink as GitHubRepoSink,  # noqa: F401
    )
    from elspeth.plugins.nodes.sinks.reproducibility_bundle import (
        ReproducibilityBundleSink as ReproducibilityBundleSink,  # noqa: F401
    )
    from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink as SignedArtifactSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.visual_report import VisualAnalyticsSink as VisualAnalyticsSink  # noqa: F401
    from elspeth.plugins.nodes.sinks.zip_bundle import ZipResultSink as ZipResultSink  # noqa: F401
# isort: on

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "AnalyticsReportSink": (
        "elspeth.plugins.nodes.sinks.analytics_report",
        "AnalyticsReportSink",
    ),
    "AzureBlobArtifactsSink": (
        "elspeth.plugins.nodes.sinks.blob",
        "AzureBlobArtifactsSink",
    ),
    "BlobResultSink": (
        "elspeth.plugins.nodes.sinks.blob",
        "BlobResultSink",
    ),
    "CsvResultSink": (
        "elspeth.plugins.nodes.sinks.csv_file",
        "CsvResultSink",
    ),
    "EmbeddingsStoreSink": (
        "elspeth.plugins.nodes.sinks.embeddings_store",
        "EmbeddingsStoreSink",
    ),
    "EnhancedVisualAnalyticsSink": (
        "elspeth.plugins.nodes.sinks.enhanced_visual_report",
        "EnhancedVisualAnalyticsSink",
    ),
    "ExcelResultSink": (
        "elspeth.plugins.nodes.sinks.excel",
        "ExcelResultSink",
    ),
    "FileCopySink": (
        "elspeth.plugins.nodes.sinks.file_copy",
        "FileCopySink",
    ),
    "LocalBundleSink": (
        "elspeth.plugins.nodes.sinks.local_bundle",
        "LocalBundleSink",
    ),
    "AzureDevOpsArtifactsRepoSink": (
        _REPOSITORY_MODULE,
        "AzureDevOpsArtifactsRepoSink",
    ),
    "AzureDevOpsRepoSink": (
        _REPOSITORY_MODULE,
        "AzureDevOpsRepoSink",
    ),
    "GitHubRepoSink": (
        _REPOSITORY_MODULE,
        "GitHubRepoSink",
    ),
    "ReproducibilityBundleSink": (
        "elspeth.plugins.nodes.sinks.reproducibility_bundle",
        "ReproducibilityBundleSink",
    ),
    "SignedArtifactSink": (
        "elspeth.plugins.nodes.sinks.signed",
        "SignedArtifactSink",
    ),
    "VisualAnalyticsSink": (
        "elspeth.plugins.nodes.sinks.visual_report",
        "VisualAnalyticsSink",
    ),
    "ZipResultSink": (
        "elspeth.plugins.nodes.sinks.zip_bundle",
        "ZipResultSink",
    ),
}


def __getattr__(name: str) -> Any:  # pragma: no cover - import-time behavior
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr = target
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:  # keep the original error for debugging
        raise ImportError(f"Cannot import {name} from {module_path}: {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ImportError(f"Module {module_path!r} does not define attribute {attr!r}") from exc


def __dir__() -> list[str]:  # pragma: no cover - trivial
    # Keep a stable, discoverable surface for IDEs and help()
    return sorted(list(globals().keys()) + __all__)
