"""
Backward compatibility shim for datasources.

DEPRECATED: This module has moved to elspeth.plugins.nodes.sources
This shim will be removed in a future major version.
"""

import warnings

# Re-export from new location
from elspeth.plugins.nodes.sources import (
    BlobDataSource,
    CSVBlobDataSource,
    CSVDataSource,
)

__all__ = ["BlobDataSource", "CSVBlobDataSource", "CSVDataSource"]

# Emit deprecation warning on import
warnings.warn(
    "elspeth.plugins.datasources is deprecated. "
    "Use elspeth.plugins.nodes.sources instead. "
    "This compatibility shim will be removed in a future major version.",
    DeprecationWarning,
    stacklevel=2,
)
