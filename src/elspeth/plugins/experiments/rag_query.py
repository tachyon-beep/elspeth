"""Backward compatibility shim for the retired RAG experiment plugin."""

from __future__ import annotations

import warnings
from typing import Any

from elspeth.plugins.utilities.retrieval import RetrievalContextUtility


class RAGQueryPlugin(RetrievalContextUtility):
    """Deprecated wrapper maintaining the old experiment plugin interface."""

    name = "rag_query"

    def __init__(self, *args, **kwargs) -> None:
        warnings.warn(
            "RAGQueryPlugin is deprecated; use RetrievalContextUtility via the utilities registry instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)

    def process_row(self, row: dict[str, Any], responses: dict[str, Any]) -> dict[str, Any]:
        """Delegate to :meth:`RetrievalContextUtility.build_payload` for compatibility."""

        return self.build_payload(row=row, responses=responses)


__all__ = ["RAGQueryPlugin"]
