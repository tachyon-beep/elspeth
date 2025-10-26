"""ADR-003 Central Plugin Registry Package.

This package contains the centralized plugin registry infrastructure:
- auto_discover.py: Automated plugin discovery (prevents bypass attacks)
- central.py: CentralPluginRegistry (unified interface)

Security Architecture:
1. Auto-discovery imports all internal plugins (forces registration)
2. Validation layer verifies expected plugins (catches bypasses)
3. Central registry provides single enforcement point (security validation)

Usage:
    >>> from elspeth.core.registry import central_registry
    >>> # Auto-discovery already ran during import
    >>> datasource = central_registry.get_datasource("local_csv", options={...})
    >>> all_plugins = central_registry.list_all_plugins()
"""

from elspeth.core.registry.auto_discover import (
    auto_discover_internal_plugins,
    validate_discovery,
)
from elspeth.core.registry.central import CentralPluginRegistry, central_registry

__all__ = [
    # Auto-discovery functions
    "auto_discover_internal_plugins",
    "validate_discovery",
    # Central registry
    "CentralPluginRegistry",
    "central_registry",
]
