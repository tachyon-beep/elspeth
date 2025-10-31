"""SecureFrameProxy for plugin worker isolation.

Provides opaque proxy handles to plugin workers (UID 1002) that marshal all
operations back to the orchestrator (UID 1000) via RPC. This prevents plugins
from accessing seal computation methods or forging seals.

Security Architecture:
- Real SecureDataFrame instances live ONLY in orchestrator process
- Plugin workers receive only SecureFrameProxy handles
- All frame operations (get_view, replace_data, uplift) go through RPC
- Proxies cannot access _compute_seal() or _verify_seal() methods
- Version tracking prevents stale snapshot reuse attacks

This design ensures:
- Seal computation isolation (plugins never touch seal code)
- Process boundary enforcement (UID 1002 cannot access UID 1000 memory)
- Audit trail generation (all mutations logged with proxy_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd

if TYPE_CHECKING:
    from elspeth.core.base.types import SecurityLevel


class OrchestratorRPCClient(Protocol):
    """Protocol for RPC client communicating with orchestrator.

    This will be implemented in Task 3.0 (worker process isolation) with
    actual Unix socket/msgpack communication. For now, it's a protocol
    defining the interface.
    """

    def call(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send RPC request to orchestrator and return response.

        Args:
            operation: RPC operation name (e.g., "get_view", "replace_data")
            params: Operation parameters

        Returns:
            Response dictionary from orchestrator

        Raises:
            ConnectionError: If RPC communication fails
            RuntimeError: If orchestrator returns error response
        """
        ...


class SecureFrameProxy:
    """Opaque proxy for SecureDataFrame (plugin worker side).

    Plugin workers receive these proxy objects instead of real SecureDataFrame
    instances. All operations marshal back to the orchestrator via RPC.

    Security Properties:
        - No access to _compute_seal() or _verify_seal() methods
        - No direct access to seal bytes or seal key
        - Cannot forge or manipulate seals
        - All mutations mediated by orchestrator
        - Version tracking prevents stale snapshot attacks

    Example:
        # In plugin worker (UID 1002):
        def my_plugin_transform(frame: SecureFrameProxy) -> SecureFrameProxy:
            # Get immutable view of data
            view = frame.get_view()

            # Mutate the snapshot
            mutated = view.copy()
            mutated['new_col'] = mutated['old_col'] * 2

            # Submit mutation back to orchestrator
            return frame.replace_data(mutated)

    Note:
        The RPC infrastructure will be implemented in Task 3.0. For now,
        this class defines the interface with stub implementations that
        raise NotImplementedError.
    """

    def __init__(
        self,
        proxy_id: str,
        rpc_client: OrchestratorRPCClient | None = None,
    ):
        """Initialize proxy with opaque handle.

        Args:
            proxy_id: Hex-encoded opaque proxy identifier
            rpc_client: RPC client for orchestrator communication
                       (None for testing, will be required in production)
        """
        self._proxy_id = proxy_id
        self._rpc_client = rpc_client
        self._version: int | None = None  # Cached view version

    @property
    def proxy_id(self) -> str:
        """Get opaque proxy identifier.

        Returns:
            Hex-encoded proxy ID
        """
        return self._proxy_id

    def get_view(self) -> tuple[pd.DataFrame, int]:
        """Get immutable snapshot of current frame data.

        Orchestrator deep-copies the frame, serializes with Arrow IPC,
        increments the version counter, and returns the snapshot.

        Returns:
            Tuple of (dataframe_snapshot, version_number)

        Raises:
            NotImplementedError: RPC not yet implemented (Task 3.0)
            ConnectionError: If RPC communication fails
            RuntimeError: If proxy is invalid or revoked

        Security:
            - Returns immutable copy (cannot mutate live frame)
            - Version tagged for mutation replay prevention
            - Orchestrator tracks which version worker has
        """
        if self._rpc_client is None:
            raise NotImplementedError(
                "RPC client not configured. "
                "SecureFrameProxy requires orchestrator RPC connection (Task 3.0)."
            )

        response = self._rpc_client.call("get_view", {"proxy_id": self._proxy_id})

        if response["status"] != "ok":
            raise RuntimeError(
                f"get_view failed: {response.get('error', 'Unknown error')}"
            )

        # Deserialize Arrow IPC bytes back to DataFrame
        # (In Task 3.0, will use pyarrow.ipc.open_stream)
        # view_data = response["view"]  # Arrow IPC bytes - will be used in Task 3.0
        version = response["version"]

        # Cache version for subsequent operations
        self._version = version

        # For now, placeholder until Arrow IPC integration in Task 3.0
        raise NotImplementedError("Arrow IPC deserialization pending Task 3.0")

    def replace_data(
        self,
        new_data: pd.DataFrame,
        version: int | None = None,
    ) -> SecureFrameProxy:
        """Submit mutated data snapshot back to orchestrator.

        Orchestrator validates the version, recomputes canonical digest,
        invokes ComputeSeal on the sidecar daemon, creates a new frame,
        and returns a fresh proxy handle.

        Args:
            new_data: Mutated DataFrame derived from get_view() snapshot
            version: Version number from get_view() (for replay prevention)
                    If None, uses cached version from last get_view()

        Returns:
            New SecureFrameProxy with updated data and fresh version

        Raises:
            NotImplementedError: RPC not yet implemented (Task 3.0)
            ValueError: If version is None and no cached version exists
            ConnectionError: If RPC communication fails
            RuntimeError: If version mismatch or orchestrator rejects mutation

        Security:
            - Version check prevents stale snapshot reuse
            - Orchestrator recomputes digest (prevents tampering)
            - Daemon computes new seal (enforces integrity)
            - Returns new proxy (prevents proxy reuse)
        """
        if version is None:
            if self._version is None:
                raise ValueError(
                    "Version must be provided or get_view() must be called first"
                )
            version = self._version

        if self._rpc_client is None:
            raise NotImplementedError(
                "RPC client not configured. "
                "SecureFrameProxy requires orchestrator RPC connection (Task 3.0)."
            )

        # Serialize DataFrame to Arrow IPC bytes
        # (In Task 3.0, will use pyarrow.ipc.new_stream)
        # For now, placeholder
        raise NotImplementedError("Arrow IPC serialization pending Task 3.0")

    def with_uplifted_security_level(
        self,
        new_level: SecurityLevel,
    ) -> SecureFrameProxy:
        """Request higher security classification.

        Orchestrator verifies current seal, requests new seal from daemon
        at higher level, creates new frame, and returns fresh proxy.

        Args:
            new_level: Requested security level (must be >= current level)

        Returns:
            New SecureFrameProxy at higher security level

        Raises:
            NotImplementedError: RPC not yet implemented (Task 3.0)
            ConnectionError: If RPC communication fails
            RuntimeError: If uplift rejected or seal verification fails

        Security:
            - Orchestrator validates current seal before uplift
            - Daemon enforces level ordering (can't downgrade)
            - New seal binds to uplifted level
            - Audit logged with proxy_id and uplift reason
        """
        if self._rpc_client is None:
            raise NotImplementedError(
                "RPC client not configured. "
                "SecureFrameProxy requires orchestrator RPC connection (Task 3.0)."
            )

        response = self._rpc_client.call(
            "with_uplifted_security_level",
            {
                "proxy_id": self._proxy_id,
                "level": new_level.value if hasattr(new_level, "value") else new_level,
            },
        )

        if response["status"] != "ok":
            raise RuntimeError(
                f"Security level uplift failed: {response.get('error', 'Unknown error')}"
            )

        # Return new proxy with uplifted level
        return SecureFrameProxy(
            proxy_id=response["new_proxy_id"],
            rpc_client=self._rpc_client,
        )

    def with_new_data(self, new_data: pd.DataFrame) -> SecureFrameProxy:
        """Replace frame data entirely (convenience wrapper for replace_data).

        Differs from replace_data() in that it doesn't require version tracking,
        making it simpler for operations that don't need snapshot consistency.

        Args:
            new_data: New DataFrame to replace current data

        Returns:
            New SecureFrameProxy with replaced data

        Raises:
            NotImplementedError: RPC not yet implemented (Task 3.0)
            ConnectionError: If RPC communication fails
            RuntimeError: If orchestrator rejects replacement

        Security:
            - Same security properties as replace_data()
            - Orchestrator recomputes digest and seal
            - No version requirement (simpler API)
        """
        if self._rpc_client is None:
            raise NotImplementedError(
                "RPC client not configured. "
                "SecureFrameProxy requires orchestrator RPC connection (Task 3.0)."
            )

        # Serialize DataFrame to Arrow IPC bytes
        # (In Task 3.0, will use pyarrow.ipc.new_stream)
        raise NotImplementedError("Arrow IPC serialization pending Task 3.0")

    @property
    def data(self) -> pd.DataFrame:
        """Get current frame data (convenience property).

        This is a convenience wrapper around get_view() that discards
        the version number. Use get_view() directly if you need version
        tracking for mutation operations.

        Returns:
            DataFrame snapshot (immutable copy)

        Raises:
            NotImplementedError: RPC not yet implemented (Task 3.0)
            ConnectionError: If RPC communication fails
            RuntimeError: If proxy is invalid or revoked
        """
        view, _ = self.get_view()
        return view

    def get_metadata(self) -> dict[str, Any]:
        """Get read-only proxy metadata without fetching data.

        Returns:
            Dictionary with keys:
            - level: Current security level
            - version: Current version number
            - audit_id: Latest audit trail identifier

        Raises:
            NotImplementedError: RPC not yet implemented (Task 3.0)
            ConnectionError: If RPC communication fails
            RuntimeError: If proxy is invalid
        """
        if self._rpc_client is None:
            raise NotImplementedError(
                "RPC client not configured. "
                "SecureFrameProxy requires orchestrator RPC connection (Task 3.0)."
            )

        response = self._rpc_client.call("get_metadata", {"proxy_id": self._proxy_id})

        if response["status"] != "ok":
            raise RuntimeError(
                f"get_metadata failed: {response.get('error', 'Unknown error')}"
            )

        return {
            "level": response["level"],
            "version": response["version"],
            "audit_id": response.get("audit_id", 0),
        }

    def __repr__(self) -> str:
        """String representation showing proxy ID."""
        return f"SecureFrameProxy(proxy_id={self._proxy_id!r})"
