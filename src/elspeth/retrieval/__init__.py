"""Retrieval utilities exposed for application and experimentation.

TODO (FEAT-002): This module will be DELETED and moved to plugins/nodes/transforms/retrieval/
                 in the namespace reorganization (BREAKING CHANGE - pre-1.0).
                 See docs/implementation/FEAT-002-namespace-reorganization.md
                 Expected: Post VULN-004 + FEAT-001 merge
"""

from .providers import QueryResult, VectorQueryClient, create_query_client
from .service import RetrievalService, create_retrieval_service

__all__ = [
    "QueryResult",
    "VectorQueryClient",
    "create_query_client",
    "RetrievalService",
    "create_retrieval_service",
]
