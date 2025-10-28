"""General-purpose utility plugins.

TODO (FEAT-002): This module will be DELETED and merged into plugins/nodes/transforms/retrieval/context.py
                 in the namespace reorganization (BREAKING CHANGE - pre-1.0).
                 See docs/implementation/FEAT-002-namespace-reorganization.md
                 Expected: Post VULN-004 + FEAT-001 merge
"""

from . import retrieval  # noqa: F401  ensure registrations

__all__ = ["retrieval"]
