# tests/engine/conftest.py
"""Shared fixtures for engine tests.

Provides common test schemas and configuration used across processor test files.
"""

from typing import Any, ClassVar

import pytest
from pydantic import ConfigDict

from elspeth.contracts import ArtifactDescriptor, PluginSchema
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape import LandscapeDB
from tests.conftest import _TestSinkBase, _TestSourceBase

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


# Shared schema for test plugins
class _TestSchema(PluginSchema):
    """Dynamic schema for test plugins."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Reusable test plugins for orchestrator tests
# ---------------------------------------------------------------------------


class ListSource(_TestSourceBase):
    """Reusable source that yields rows from a list.

    Usage:
        source = ListSource([{"value": 1}, {"value": 2}])
        # or with custom name:
        source = ListSource([{"value": 1}], name="my_source")
    """

    output_schema = _TestSchema

    def __init__(self, data: list[dict[str, Any]], name: str = "list_source") -> None:
        super().__init__()
        self._data = data
        self.name = name

    def on_start(self, ctx: Any) -> None:
        pass

    def load(self, ctx: Any) -> Any:
        yield from self.wrap_rows(self._data)

    def close(self) -> None:
        pass


class CollectSink(_TestSinkBase):
    """Reusable sink that collects results into a list.

    Usage:
        sink = CollectSink()
        # ... run pipeline ...
        assert sink.results == [{"value": 1}, {"value": 2}]

        # With custom name:
        sink = CollectSink("output_sink")

        # With node_id (for tests that need it):
        sink = CollectSink("output", node_id="sink_node_123")
    """

    def __init__(self, name: str = "collect", *, node_id: str | None = None) -> None:
        self.name = name
        self.node_id = node_id
        self.results: list[dict[str, Any]] = []
        self._artifact_counter = 0

    @property
    def rows_written(self) -> list[dict[str, Any]]:
        """Alias for results - some tests use this name."""
        return self.results

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
        self.results.extend(rows)
        self._artifact_counter += 1
        return ArtifactDescriptor.for_file(
            path=f"memory://{self.name}_{self._artifact_counter}",
            size_bytes=len(str(rows)),
            content_hash=f"hash_{self._artifact_counter}",
        )

    def close(self) -> None:
        pass


@pytest.fixture(scope="module")
def landscape_db() -> LandscapeDB:
    """Module-scoped in-memory database for engine tests.

    Each test gets a unique run_id via recorder.begin_run(), ensuring
    test isolation while sharing the database connection overhead.
    """
    return LandscapeDB.in_memory()
