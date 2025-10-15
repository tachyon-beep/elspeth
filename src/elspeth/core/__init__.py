"""Core orchestration components for ELSPETH."""

from .protocols import DataSource, LLMClientProtocol, ResultSink

__all__ = [
    "DataSource",
    "LLMClientProtocol",
    "ResultSink",
]
