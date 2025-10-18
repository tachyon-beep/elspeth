"""Sink nodes - output vertices in the data flow graph."""

from elspeth.plugins.nodes.sinks.analytics_report import AnalyticsReportSink
from elspeth.plugins.nodes.sinks.blob import BlobResultSink
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink
from elspeth.plugins.nodes.sinks.embeddings_store import EmbeddingsStoreSink
from elspeth.plugins.nodes.sinks.enhanced_visual_report import EnhancedVisualAnalyticsSink
from elspeth.plugins.nodes.sinks.excel import ExcelResultSink
from elspeth.plugins.nodes.sinks.file_copy import FileCopySink
from elspeth.plugins.nodes.sinks.local_bundle import LocalBundleSink
from elspeth.plugins.nodes.sinks.repository import (
    AzureDevOpsArtifactsRepoSink,
    AzureDevOpsRepoSink,
    GitHubRepoSink,
)
from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink
from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink
from elspeth.plugins.nodes.sinks.visual_report import VisualAnalyticsSink
from elspeth.plugins.nodes.sinks.zip_bundle import ZipResultSink

__all__ = [
    "BlobResultSink",
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
