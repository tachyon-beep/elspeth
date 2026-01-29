# tests/property/sinks/test_artifact_properties.py
"""Property-based tests for sink artifact descriptors.

Sink artifacts are recorded in the audit trail. Their content hashes
must be deterministic - same content must always produce same hash.

These tests verify:
- Content hash determinism
- Artifact descriptor immutability
- Size reporting accuracy
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.core.canonical import stable_hash
from elspeth.engine.artifacts import ArtifactDescriptor
from tests.property.conftest import MAX_SAFE_INT, MIN_SAFE_INT

# =============================================================================
# Strategies
# =============================================================================

# File paths without file:// prefix (for_file adds it)
file_paths = st.text(
    min_size=1,
    max_size=100,
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789/_-.",
)

content_hashes = st.text(
    min_size=64,
    max_size=64,
    alphabet="0123456789abcdef",
)

sizes = st.integers(min_value=0, max_value=10_000_000)

# RFC 8785 safe integers for row values
safe_integers = st.integers(min_value=MIN_SAFE_INT, max_value=MAX_SAFE_INT)


# =============================================================================
# ArtifactDescriptor Property Tests
# =============================================================================


class TestArtifactDescriptorProperties:
    """Property tests for ArtifactDescriptor."""

    @given(path=file_paths, size=sizes, content_hash=content_hashes)
    @settings(max_examples=100)
    def test_for_file_creates_valid_descriptor(self, path: str, size: int, content_hash: str) -> None:
        """Property: for_file() creates descriptor with correct fields."""
        descriptor = ArtifactDescriptor.for_file(
            path=path,
            size_bytes=size,
            content_hash=content_hash,
        )

        # for_file() adds file:// prefix
        assert descriptor.path_or_uri == f"file://{path}"
        assert descriptor.size_bytes == size
        assert descriptor.content_hash == content_hash
        assert descriptor.artifact_type == "file"

    @given(path=file_paths, size=sizes, content_hash=content_hashes)
    @settings(max_examples=50)
    def test_descriptor_creation_is_deterministic(self, path: str, size: int, content_hash: str) -> None:
        """Property: Same inputs produce equal descriptors."""
        d1 = ArtifactDescriptor.for_file(path=path, size_bytes=size, content_hash=content_hash)
        d2 = ArtifactDescriptor.for_file(path=path, size_bytes=size, content_hash=content_hash)

        assert d1.path_or_uri == d2.path_or_uri
        assert d1.size_bytes == d2.size_bytes
        assert d1.content_hash == d2.content_hash
        assert d1.artifact_type == d2.artifact_type

    @given(path=file_paths, size=sizes, content_hash=content_hashes)
    @settings(max_examples=50)
    def test_descriptor_is_frozen(self, path: str, size: int, content_hash: str) -> None:
        """Property: ArtifactDescriptor is immutable (frozen dataclass)."""
        descriptor = ArtifactDescriptor.for_file(
            path=path,
            size_bytes=size,
            content_hash=content_hash,
        )

        # Attempt to mutate should raise FrozenInstanceError
        import pytest

        with pytest.raises(AttributeError):
            descriptor.content_hash = "modified"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            descriptor.size_bytes = 999  # type: ignore[misc]


class TestContentHashDeterminism:
    """Property tests for content hash determinism in sinks."""

    @given(content=st.binary(min_size=0, max_size=10_000))
    @settings(max_examples=100)
    def test_binary_content_hash_deterministic(self, content: bytes) -> None:
        """Property: Same binary content always produces same hash."""
        # Simulate what a sink would do
        hash1 = stable_hash({"content": content})
        hash2 = stable_hash({"content": content})

        assert hash1 == hash2

    @given(
        rows=st.lists(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=10),
                values=st.one_of(safe_integers, st.text(max_size=20)),
                min_size=1,
                max_size=5,
            ),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_row_batch_hash_deterministic(self, rows: list[dict[str, Any]]) -> None:
        """Property: Same row batch always produces same hash."""
        hash1 = stable_hash({"rows": rows})
        hash2 = stable_hash({"rows": rows})

        assert hash1 == hash2

    @given(
        content=st.binary(min_size=0, max_size=1000),
        size=sizes,
    )
    @settings(max_examples=50)
    def test_descriptor_with_computed_hash(self, content: bytes, size: int) -> None:
        """Property: Descriptor hash matches recomputed hash from same content."""
        content_hash = stable_hash({"content": content})

        descriptor = ArtifactDescriptor.for_file(
            path="test/output.csv",
            size_bytes=size,
            content_hash=content_hash,
        )

        # Recompute hash - should match
        recomputed_hash = stable_hash({"content": content})
        assert descriptor.content_hash == recomputed_hash
