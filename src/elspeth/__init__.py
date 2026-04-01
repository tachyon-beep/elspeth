"""
Elspeth: Auditable Sense/Decide/Act pipelines for high-reliability systems.

A framework for building data processing workflows where every decision
must be traceable to its source.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("elspeth")
except PackageNotFoundError:
    # Development install without package metadata (e.g., editable install not yet run)
    __version__ = "0.0.0-dev"
