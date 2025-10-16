"""Core orchestration components for ELSPETH."""

from .plugin_context import PluginContext, apply_plugin_context
from .protocols import DataSource, LLMClientProtocol, ResultSink

__all__ = [
    "DataSource",
    "LLMClientProtocol",
    "PluginContext",
    "ResultSink",
    "apply_plugin_context",
]
