"""Sink nodes - output vertices in the data flow graph.

This package exposes many optional sinks that depend on third‑party services
and libraries (e.g., Azure SDKs, psycopg/pgvector). To keep imports lightweight
and avoid import‑time failures in environments where those optional deps are not
installed (such as CI when only a subset is needed), we lazily import sink
implementations on first attribute access.

Clients may continue to do ``from elspeth.plugins.nodes.sinks import FooSink``;
the symbol will be loaded on demand.
"""

from __future__ import annotations

import importlib
from typing import Any

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
        raise ImportError(
            f"Cannot import {name} from {module_path}: {exc}"
        ) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ImportError(
            f"Module {module_path!r} does not define attribute {attr!r}"
        ) from exc


def __dir__() -> list[str]:  # pragma: no cover - trivial
    # Keep a stable, discoverable surface for IDEs and help()
    return sorted(list(globals().keys()) + __all__)
