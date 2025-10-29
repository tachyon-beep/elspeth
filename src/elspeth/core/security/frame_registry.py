"""Frame registry for stable UUID tracking and digest caching.

Maintains process-local mapping from frame_id (UUID) → SecureDataFrame metadata.
This ensures:
- Stable identifiers (no pointer reuse vulnerabilities)
- Digest caching (read-only operations stay O(1))
- Audit traceability (UUIDs enable log correlation)

Security Properties:
- Frame IDs are never reused (even after deregistration)
- Digest updates only after orchestrator-approved mutations
- Thread-safe access via locks
- Fail-fast on unknown frame_id lookups

Architecture:
The registry is owned by the orchestrator process and bridges the gap between
the sidecar daemon (which tracks registered frame_ids for seal validation) and
the Python application layer (which holds actual DataFrame instances).
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from elspeth.core.security.secure_data import SecureDataFrame


@dataclass(frozen=True)
class FrameRegistryEntry:
    """Registry entry containing frame metadata.

    Attributes:
        frame: The SecureDataFrame instance
        digest: 32-byte BLAKE3 digest of canonical Parquet representation
        level: Security level (0=UNOFFICIAL through 4=SECRET)
        created_at: Unix timestamp when frame was registered
    """

    frame: SecureDataFrame
    digest: bytes
    level: int
    created_at: float

    def __post_init__(self) -> None:
        """Validate entry fields."""
        if len(self.digest) != 32:
            raise ValueError(f"Digest must be 32 bytes, got {len(self.digest)}")
        if not (0 <= self.level <= 4):
            raise ValueError(f"Security level must be 0-4, got {self.level}")


class FrameRegistry:
    """Process-local registry mapping frame_id → SecureDataFrame metadata.

    Provides stable UUID-based frame tracking with digest caching to avoid
    repeated Parquet serialization on read-only operations.

    Thread-Safety:
        All public methods are thread-safe via internal locking.

    Example:
        registry = FrameRegistry()

        # Register new frame
        frame_id = uuid4()
        registry.register(frame_id, frame, digest, level=2)

        # Lookup frame metadata
        entry = registry.lookup(frame_id)
        print(f"Frame level: {entry.level}, digest: {entry.digest.hex()}")

        # Update digest after mutation
        new_digest = compute_dataframe_digest(entry.frame.data)
        registry.update_digest(frame_id, new_digest)

        # Cleanup when done
        registry.deregister(frame_id)
    """

    def __init__(self) -> None:
        """Initialize empty frame registry."""
        self._frames: dict[UUID, FrameRegistryEntry] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested operations
        self._deregistered_ids: set[UUID] = set()  # Track to prevent reuse

    def register(
        self,
        frame_id: UUID,
        frame: SecureDataFrame,
        digest: bytes,
        level: int,
    ) -> None:
        """Register a new frame in the registry.

        Args:
            frame_id: Unique UUID for this frame (must not be reused)
            frame: SecureDataFrame instance to track
            digest: 32-byte BLAKE3 digest of canonical data
            level: Security level (0-4)

        Raises:
            ValueError: If frame_id was previously used (even if deregistered)
            ValueError: If frame_id is already registered
            ValueError: If digest is not 32 bytes
            ValueError: If level is not 0-4
        """
        with self._lock:
            if frame_id in self._deregistered_ids:
                raise ValueError(
                    f"Frame ID {frame_id} was previously used and cannot be reused. "
                    "Generate a new UUID for this frame."
                )

            if frame_id in self._frames:
                raise ValueError(
                    f"Frame ID {frame_id} is already registered. "
                    "Cannot register the same frame_id twice."
                )

            entry = FrameRegistryEntry(
                frame=frame,
                digest=digest,
                level=level,
                created_at=time.time(),
            )

            self._frames[frame_id] = entry

    def lookup(self, frame_id: UUID) -> FrameRegistryEntry:
        """Retrieve registry entry for a frame.

        Args:
            frame_id: UUID of frame to lookup

        Returns:
            FrameRegistryEntry containing frame metadata

        Raises:
            KeyError: If frame_id is not registered
        """
        with self._lock:
            if frame_id not in self._frames:
                raise KeyError(
                    f"Frame ID {frame_id} not found in registry. "
                    "Ensure frame was registered via authorize/redeem flow."
                )
            return self._frames[frame_id]

    def contains(self, frame_id: UUID) -> bool:
        """Check if frame_id is registered.

        Args:
            frame_id: UUID to check

        Returns:
            True if frame_id is registered, False otherwise
        """
        with self._lock:
            return frame_id in self._frames

    def update_digest(self, frame_id: UUID, new_digest: bytes) -> None:
        """Update cached digest after frame mutation.

        Should only be called after orchestrator-approved mutations
        (e.g., with_new_data, replace_data). Read-only operations
        should reuse the cached digest.

        Args:
            frame_id: UUID of frame to update
            new_digest: 32-byte BLAKE3 digest of new canonical data

        Raises:
            KeyError: If frame_id is not registered
            ValueError: If new_digest is not 32 bytes
        """
        if len(new_digest) != 32:
            raise ValueError(f"Digest must be 32 bytes, got {len(new_digest)}")

        with self._lock:
            if frame_id not in self._frames:
                raise KeyError(
                    f"Frame ID {frame_id} not found in registry. "
                    "Cannot update digest for unregistered frame."
                )

            # Create new entry with updated digest
            old_entry = self._frames[frame_id]
            new_entry = FrameRegistryEntry(
                frame=old_entry.frame,
                digest=new_digest,
                level=old_entry.level,
                created_at=old_entry.created_at,
            )
            self._frames[frame_id] = new_entry

    def deregister(self, frame_id: UUID) -> None:
        """Remove frame from registry and mark ID as permanently retired.

        The frame_id is moved to the deregistered set to prevent future
        reuse, ensuring stable identifier semantics.

        Args:
            frame_id: UUID of frame to deregister

        Raises:
            KeyError: If frame_id is not registered
        """
        with self._lock:
            if frame_id not in self._frames:
                raise KeyError(
                    f"Frame ID {frame_id} not found in registry. "
                    "Cannot deregister unregistered frame."
                )

            # Remove from active registry
            del self._frames[frame_id]

            # Mark as permanently retired (prevents reuse)
            self._deregistered_ids.add(frame_id)

    def active_count(self) -> int:
        """Return count of currently registered frames.

        Returns:
            Number of active frames in registry
        """
        with self._lock:
            return len(self._frames)

    def list_frame_ids(self) -> list[UUID]:
        """Return list of all registered frame IDs.

        Returns:
            List of UUIDs for all active frames (snapshot)
        """
        with self._lock:
            return list(self._frames.keys())
