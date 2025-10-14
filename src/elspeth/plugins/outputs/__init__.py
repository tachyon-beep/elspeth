"""
Backward compatibility shim for output sinks.

DEPRECATED: This module has moved to elspeth.plugins.nodes.sinks
This shim will be removed in a future major version.
"""

import warnings

# Re-export from new location
from elspeth.plugins.nodes.sinks import (
    AnalyticsReportSink,
    AzureDevOpsRepoSink,
    BlobResultSink,
    CsvResultSink,
    EmbeddingsStoreSink,
    EnhancedVisualAnalyticsSink,
    ExcelResultSink,
    FileCopySink,
    GitHubRepoSink,
    LocalBundleSink,
    SignedArtifactSink,
    VisualAnalyticsSink,
    ZipResultSink,
)

__all__ = [
    "BlobResultSink",
    "CsvResultSink",
    "LocalBundleSink",
    "ExcelResultSink",
    "ZipResultSink",
    "FileCopySink",
    "GitHubRepoSink",
    "AzureDevOpsRepoSink",
    "SignedArtifactSink",
    "AnalyticsReportSink",
    "VisualAnalyticsSink",
    "EnhancedVisualAnalyticsSink",
    "EmbeddingsStoreSink",
]

# Emit deprecation warning on import
warnings.warn(
    "elspeth.plugins.outputs is deprecated. "
    "Use elspeth.plugins.nodes.sinks instead. "
    "This compatibility shim will be removed in a future major version.",
    DeprecationWarning,
    stacklevel=2,
)
