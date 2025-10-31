"""Tests for FrameRegistry stable UUID tracking."""

from uuid import uuid4
import pytest
import pandas as pd

from elspeth.core.security.frame_registry import FrameRegistry, FrameRegistryEntry


# Mock SecureDataFrame for testing (avoids circular dependencies)
class MockSecureDataFrame:
    """Minimal mock of SecureDataFrame for registry testing."""

    def __init__(self, data: pd.DataFrame, level: int = 0):
        self.data = data
        self.security_level_int = level


def test_frame_registry_entry_validation():
    """Test FrameRegistryEntry validates digest and level."""
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=2)
    digest = b"\x01" * 32

    # Valid entry
    entry = FrameRegistryEntry(
        frame=frame,
        digest=digest,
        level=2,
        created_at=1000.0,
    )
    assert entry.frame == frame
    assert entry.digest == digest
    assert entry.level == 2

    # Invalid digest length
    with pytest.raises(ValueError, match="Digest must be 32 bytes"):
        FrameRegistryEntry(
            frame=frame,
            digest=b"\x01" * 16,  # Wrong length
            level=2,
            created_at=1000.0,
        )

    # Invalid security level
    with pytest.raises(ValueError, match="Security level must be 0-4"):
        FrameRegistryEntry(
            frame=frame,
            digest=digest,
            level=5,  # Too high
            created_at=1000.0,
        )


def test_frame_registry_register_and_lookup():
    """Test registering and looking up frames."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=2)
    digest = b"\xaa" * 32

    # Register frame
    registry.register(frame_id, frame, digest, level=2)

    # Lookup frame
    entry = registry.lookup(frame_id)
    assert entry.frame == frame
    assert entry.digest == digest
    assert entry.level == 2
    assert entry.created_at > 0


def test_frame_registry_contains():
    """Test checking if frame_id exists."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=1)
    digest = b"\xbb" * 32

    # Not registered yet
    assert not registry.contains(frame_id)

    # Register
    registry.register(frame_id, frame, digest, level=1)

    # Now registered
    assert registry.contains(frame_id)


def test_frame_registry_double_registration_fails():
    """Test that registering same frame_id twice fails."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=0)
    digest = b"\xcc" * 32

    # First registration succeeds
    registry.register(frame_id, frame, digest, level=0)

    # Second registration fails
    with pytest.raises(ValueError, match="already registered"):
        registry.register(frame_id, frame, digest, level=0)


def test_frame_registry_prevents_id_reuse():
    """Test that deregistered IDs cannot be reused."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=1)
    digest = b"\xdd" * 32

    # Register and deregister
    registry.register(frame_id, frame, digest, level=1)
    registry.deregister(frame_id)

    # Attempting to reuse ID fails
    with pytest.raises(ValueError, match="previously used and cannot be reused"):
        registry.register(frame_id, frame, digest, level=1)


def test_frame_registry_lookup_unknown_frame_fails():
    """Test that looking up unknown frame_id raises KeyError."""
    registry = FrameRegistry()
    unknown_id = uuid4()

    with pytest.raises(KeyError, match="not found in registry"):
        registry.lookup(unknown_id)


def test_frame_registry_update_digest():
    """Test updating cached digest after mutation."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=2)
    old_digest = b"\xaa" * 32
    new_digest = b"\xbb" * 32

    # Register with old digest
    registry.register(frame_id, frame, old_digest, level=2)

    # Verify old digest
    entry = registry.lookup(frame_id)
    assert entry.digest == old_digest

    # Update digest
    registry.update_digest(frame_id, new_digest)

    # Verify new digest
    entry = registry.lookup(frame_id)
    assert entry.digest == new_digest
    assert entry.frame == frame  # Frame reference unchanged
    assert entry.level == 2  # Level unchanged


def test_frame_registry_update_digest_validation():
    """Test that update_digest validates digest length."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=1)
    digest = b"\xcc" * 32

    registry.register(frame_id, frame, digest, level=1)

    # Invalid digest length
    with pytest.raises(ValueError, match="Digest must be 32 bytes"):
        registry.update_digest(frame_id, b"\x01" * 16)


def test_frame_registry_update_digest_unknown_frame():
    """Test that updating digest for unknown frame fails."""
    registry = FrameRegistry()
    unknown_id = uuid4()
    new_digest = b"\xdd" * 32

    with pytest.raises(KeyError, match="not found in registry"):
        registry.update_digest(unknown_id, new_digest)


def test_frame_registry_deregister():
    """Test deregistering frames."""
    registry = FrameRegistry()
    frame_id = uuid4()
    frame = MockSecureDataFrame(pd.DataFrame({"a": [1, 2, 3]}), level=0)
    digest = b"\xee" * 32

    # Register frame
    registry.register(frame_id, frame, digest, level=0)
    assert registry.contains(frame_id)

    # Deregister frame
    registry.deregister(frame_id)
    assert not registry.contains(frame_id)

    # Lookup now fails
    with pytest.raises(KeyError, match="not found in registry"):
        registry.lookup(frame_id)


def test_frame_registry_deregister_unknown_frame():
    """Test that deregistering unknown frame fails."""
    registry = FrameRegistry()
    unknown_id = uuid4()

    with pytest.raises(KeyError, match="not found in registry"):
        registry.deregister(unknown_id)


def test_frame_registry_active_count():
    """Test counting active frames."""
    registry = FrameRegistry()

    # Empty registry
    assert registry.active_count() == 0

    # Add 3 frames
    for i in range(3):
        frame_id = uuid4()
        frame = MockSecureDataFrame(pd.DataFrame({"a": [i]}), level=0)
        digest = bytes([i]) * 32
        registry.register(frame_id, frame, digest, level=0)

    assert registry.active_count() == 3

    # Deregister 1 frame
    frame_id = registry.list_frame_ids()[0]
    registry.deregister(frame_id)

    assert registry.active_count() == 2


def test_frame_registry_list_frame_ids():
    """Test listing all frame IDs."""
    registry = FrameRegistry()

    # Empty registry
    assert registry.list_frame_ids() == []

    # Add 3 frames
    frame_ids = []
    for i in range(3):
        frame_id = uuid4()
        frame_ids.append(frame_id)
        frame = MockSecureDataFrame(pd.DataFrame({"a": [i]}), level=0)
        digest = bytes([i]) * 32
        registry.register(frame_id, frame, digest, level=0)

    # List should contain all frame IDs
    listed_ids = registry.list_frame_ids()
    assert len(listed_ids) == 3
    assert set(listed_ids) == set(frame_ids)


def test_frame_registry_multiple_frames():
    """Test registering and managing multiple frames."""
    registry = FrameRegistry()

    # Create 5 frames with different levels
    frames_data = []
    for i in range(5):
        frame_id = uuid4()
        frame = MockSecureDataFrame(pd.DataFrame({"a": [i, i+1, i+2]}), level=i % 5)
        digest = bytes([i]) * 32
        frames_data.append((frame_id, frame, digest, i % 5))
        registry.register(frame_id, frame, digest, level=i % 5)

    # Verify all frames can be looked up
    for frame_id, expected_frame, expected_digest, expected_level in frames_data:
        entry = registry.lookup(frame_id)
        assert entry.frame == expected_frame
        assert entry.digest == expected_digest
        assert entry.level == expected_level

    # Deregister every other frame
    for i, (frame_id, _, _, _) in enumerate(frames_data):
        if i % 2 == 0:
            registry.deregister(frame_id)

    # Verify count
    assert registry.active_count() == 2
