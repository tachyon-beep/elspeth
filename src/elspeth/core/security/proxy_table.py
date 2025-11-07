"""ProxyTable for tracking SecureFrameProxy mappings in orchestrator.

The orchestrator maintains a table mapping proxy_id (opaque handles given to
workers) to actual frame metadata. This enables:
- Proxy handle validation
- Version tracking for mutation operations
- Audit trail generation
- Proxy lifecycle management (creation, updates, revocation)

Security Properties:
- Proxy IDs are cryptographically random (UUID4)
- Workers cannot guess valid proxy IDs
- Stale proxy IDs fail validation
- Version mismatches detected and logged
- All operations auditable via proxy_id → frame_id mapping
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class ProxyEntry:
    """Entry tracking proxy-to-frame mapping.

    Attributes:
        proxy_id: Opaque proxy handle (hex-encoded UUID)
        frame_id: Real frame identifier in FrameRegistry
        version: Current version number (increments on mutations)
        created_at: Unix timestamp when proxy was created
        last_accessed: Unix timestamp of last operation
    """

    proxy_id: str
    frame_id: UUID
    version: int
    created_at: float
    last_accessed: float

    def with_incremented_version(self) -> ProxyEntry:
        """Create new entry with version incremented.

        Returns:
            New ProxyEntry with version+1 and updated last_accessed
        """
        return ProxyEntry(
            proxy_id=self.proxy_id,
            frame_id=self.frame_id,
            version=self.version + 1,
            created_at=self.created_at,
            last_accessed=time.time(),
        )

    def with_updated_access_time(self) -> ProxyEntry:
        """Create new entry with updated last_accessed timestamp.

        Returns:
            New ProxyEntry with current timestamp
        """
        return ProxyEntry(
            proxy_id=self.proxy_id,
            frame_id=self.frame_id,
            version=self.version,
            created_at=self.created_at,
            last_accessed=time.time(),
        )


class ProxyTable:
    """Orchestrator-side table mapping proxy IDs to frame metadata.

    Maintains the mapping between opaque proxy handles (given to workers)
    and actual SecureDataFrame instances (stored in FrameRegistry).

    Thread-Safety:
        All public methods are thread-safe via internal locking.

    Example:
        table = ProxyTable()

        # Create proxy for a frame
        proxy_id = table.create_proxy(frame_id)

        # Worker requests view
        entry = table.lookup(proxy_id)
        print(f"Frame ID: {entry.frame_id}, Version: {entry.version}")

        # After mutation, increment version
        table.increment_version(proxy_id)

        # Revoke proxy when done
        table.revoke(proxy_id)
    """

    def __init__(self) -> None:
        """Initialize empty proxy table."""
        self._proxies: dict[str, ProxyEntry] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested operations
        self._revoked_ids: set[str] = set()  # Track revoked proxies

    def create_proxy(self, frame_id: UUID) -> str:
        """Create new proxy handle for a frame.

        Args:
            frame_id: UUID of frame in FrameRegistry

        Returns:
            Hex-encoded proxy ID (opaque handle for workers)
        """
        with self._lock:
            # Generate cryptographically random proxy ID
            proxy_id = uuid4().hex

            entry = ProxyEntry(
                proxy_id=proxy_id,
                frame_id=frame_id,
                version=1,  # Initial version
                created_at=time.time(),
                last_accessed=time.time(),
            )

            self._proxies[proxy_id] = entry

            return proxy_id

    def lookup(self, proxy_id: str) -> ProxyEntry:
        """Lookup proxy entry and update access time.

        Args:
            proxy_id: Hex-encoded proxy handle

        Returns:
            ProxyEntry with frame metadata

        Raises:
            KeyError: If proxy_id is invalid or revoked
        """
        with self._lock:
            if proxy_id in self._revoked_ids:
                raise KeyError(
                    f"Proxy ID {proxy_id} has been revoked and cannot be used"
                )

            if proxy_id not in self._proxies:
                raise KeyError(
                    f"Proxy ID {proxy_id} not found. "
                    "Proxy may have been revoked or never existed."
                )

            # Update access time
            entry = self._proxies[proxy_id]
            updated_entry = entry.with_updated_access_time()
            self._proxies[proxy_id] = updated_entry

            return updated_entry

    def contains(self, proxy_id: str) -> bool:
        """Check if proxy ID exists and is not revoked.

        Args:
            proxy_id: Hex-encoded proxy handle

        Returns:
            True if proxy is valid and not revoked
        """
        with self._lock:
            return (
                proxy_id in self._proxies
                and proxy_id not in self._revoked_ids
            )

    def increment_version(self, proxy_id: str) -> ProxyEntry:
        """Increment proxy version after successful mutation.

        Args:
            proxy_id: Hex-encoded proxy handle

        Returns:
            Updated ProxyEntry with version+1

        Raises:
            KeyError: If proxy_id is invalid or revoked
        """
        with self._lock:
            if proxy_id in self._revoked_ids:
                raise KeyError(
                    f"Proxy ID {proxy_id} has been revoked and cannot be updated"
                )

            if proxy_id not in self._proxies:
                raise KeyError(
                    f"Proxy ID {proxy_id} not found"
                )

            entry = self._proxies[proxy_id]
            updated_entry = entry.with_incremented_version()
            self._proxies[proxy_id] = updated_entry

            return updated_entry

    def update_frame_id(self, proxy_id: str, new_frame_id: UUID) -> ProxyEntry:
        """Update frame_id after replace_data creates new frame.

        When a worker submits mutated data via replace_data(), the orchestrator
        creates a NEW frame in the FrameRegistry. We need to update the proxy
        to point to this new frame while preserving the proxy_id.

        Args:
            proxy_id: Hex-encoded proxy handle
            new_frame_id: UUID of newly created frame

        Returns:
            Updated ProxyEntry pointing to new frame

        Raises:
            KeyError: If proxy_id is invalid or revoked
        """
        with self._lock:
            if proxy_id in self._revoked_ids:
                raise KeyError(
                    f"Proxy ID {proxy_id} has been revoked and cannot be updated"
                )

            if proxy_id not in self._proxies:
                raise KeyError(
                    f"Proxy ID {proxy_id} not found"
                )

            entry = self._proxies[proxy_id]

            # Create new entry with updated frame_id and incremented version
            updated_entry = ProxyEntry(
                proxy_id=proxy_id,
                frame_id=new_frame_id,
                version=entry.version + 1,
                created_at=entry.created_at,
                last_accessed=time.time(),
            )

            self._proxies[proxy_id] = updated_entry

            return updated_entry

    def revoke(self, proxy_id: str) -> None:
        """Revoke proxy and prevent future use.

        Args:
            proxy_id: Hex-encoded proxy handle to revoke

        Raises:
            KeyError: If proxy_id not found
        """
        with self._lock:
            if proxy_id not in self._proxies:
                raise KeyError(
                    f"Proxy ID {proxy_id} not found. Cannot revoke non-existent proxy."
                )

            # Move to revoked set
            del self._proxies[proxy_id]
            self._revoked_ids.add(proxy_id)

    def active_count(self) -> int:
        """Return count of active (non-revoked) proxies.

        Returns:
            Number of active proxies
        """
        with self._lock:
            return len(self._proxies)

    def cleanup_stale(self, max_age_seconds: float) -> int:
        """Remove proxies not accessed within max_age_seconds.

        Args:
            max_age_seconds: Maximum age for keeping inactive proxies

        Returns:
            Number of proxies removed
        """
        with self._lock:
            now = time.time()
            stale_ids = [
                proxy_id
                for proxy_id, entry in self._proxies.items()
                if (now - entry.last_accessed) > max_age_seconds
            ]

            for proxy_id in stale_ids:
                del self._proxies[proxy_id]
                self._revoked_ids.add(proxy_id)

            return len(stale_ids)

    def list_proxy_ids(self) -> list[str]:
        """Return list of all active proxy IDs.

        Returns:
            List of hex-encoded proxy IDs (snapshot)
        """
        with self._lock:
            return list(self._proxies.keys())
