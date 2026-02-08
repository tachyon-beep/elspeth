# tests/property/conftest.py
"""Property test configuration.

Imports strategies from tests/strategies/ modules.
No database fixtures — property tests are pure logic.
"""

from typing import ClassVar

from pydantic import ConfigDict

from tests.fixtures.base_classes import _TestSchema


class PropertyTestSchema(_TestSchema):
    """Schema for property tests — accepts any dict with dynamic fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
