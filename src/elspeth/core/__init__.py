"""Core orchestration components for ELSPETH."""

from .interfaces import DataSource, LLMClientProtocol, ResultSink

__all__ = [
    "DataSource",
    "LLMClientProtocol",
    "ResultSink",
]
