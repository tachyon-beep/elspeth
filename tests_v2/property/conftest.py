# tests_v2/property/conftest.py
"""Property test configuration.

Imports strategies from tests_v2/strategies/ modules.
No database fixtures — property tests are pure logic.
"""

from typing import ClassVar

from pydantic import ConfigDict

from tests_v2.fixtures.base_classes import _TestSchema


class PropertyTestSchema(_TestSchema):
    """Schema for property tests — accepts any dict with dynamic fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
