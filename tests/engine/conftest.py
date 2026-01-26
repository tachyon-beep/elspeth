# tests/engine/conftest.py
"""Shared fixtures for engine tests.

Provides common test schemas and configuration used across processor test files.
"""

from typing import ClassVar

from pydantic import ConfigDict

from elspeth.contracts import PluginSchema
from elspeth.contracts.schema import SchemaConfig

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"fields": "dynamic"})


# Shared schema for test plugins
class _TestSchema(PluginSchema):
    """Dynamic schema for test plugins."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
