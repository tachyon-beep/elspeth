# tests/unit/engine/conftest.py
"""Engine unit test fixtures."""

from typing import ClassVar

from pydantic import ConfigDict

from elspeth.contracts import PluginSchema
from elspeth.contracts.schema import SchemaConfig

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


class _TestSchema(PluginSchema):
    """Dynamic schema for engine test plugins."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
