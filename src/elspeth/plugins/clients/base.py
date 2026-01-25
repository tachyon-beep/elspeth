# src/elspeth/plugins/clients/base.py
"""Base class for audited clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder


class AuditedClientBase:
    """Base class for clients that automatically record to audit trail.

    Provides common infrastructure for tracking external calls:
    - Reference to LandscapeRecorder for audit storage and call index allocation
    - State ID linking calls to the current processing state

    Subclasses implement specific client protocols (LLM, HTTP, etc.)
    while inheriting automatic audit recording.

    Thread Safety:
        The _next_call_index method delegates to LandscapeRecorder.allocate_call_index(),
        which is thread-safe. Multiple threads and multiple client types can safely
        call this method concurrently without risk of call_index collisions.

    Call Index Coordination:
        Call indices are allocated centrally by the LandscapeRecorder, ensuring
        UNIQUE(state_id, call_index) across all client types (HTTP, LLM) and retry
        attempts. This prevents IntegrityError when multiple clients share the same state_id.
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        state_id: str,
    ) -> None:
        """Initialize audited client.

        Args:
            recorder: LandscapeRecorder for audit trail storage and call index allocation
            state_id: Node state ID to associate calls with
        """
        self._recorder = recorder
        self._state_id = state_id

    def _next_call_index(self) -> int:
        """Get next call index for this state (thread-safe).

        Delegates to LandscapeRecorder for centralized call index allocation.
        This ensures unique indices across all client types sharing the same state_id.

        Returns:
            Sequential call index, unique within this state_id (not just this client)
        """
        return self._recorder.allocate_call_index(self._state_id)
