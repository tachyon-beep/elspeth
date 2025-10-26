"""ADR-003 Central Plugin Registry Package.

This package contains the centralized plugin registry infrastructure:
- auto_discover.py: Automated plugin discovery (prevents bypass attacks)
- central.py: CentralPluginRegistry (unified interface) [Phase 2]

Security Architecture:
1. Auto-discovery imports all internal plugins (forces registration)
2. Validation layer verifies expected plugins (catches bypasses)
3. Central registry provides single enforcement point (security validation)

Usage:
    >>> from elspeth.core.registry import registry  # Phase 2
    >>> from elspeth.core.registry.auto_discover import auto_discover_internal_plugins
    >>> auto_discover_internal_plugins()
"""

from elspeth.core.registry.auto_discover import (
    auto_discover_internal_plugins,
    validate_discovery,
)

__all__ = [
    "auto_discover_internal_plugins",
    "validate_discovery",
]
