"""Suite reporting tools.

TODO (FEAT-002): This module will be DELETED and moved to plugins/nodes/sinks/reporting/
                 in the namespace reorganization (BREAKING CHANGE - pre-1.0).
                 See docs/implementation/FEAT-002-namespace-reorganization.md
                 Expected: Post VULN-004 + FEAT-001 merge
"""

from .reporting import SuiteReportGenerator

__all__ = ["SuiteReportGenerator"]
