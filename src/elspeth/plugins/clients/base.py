# src/elspeth/plugins/clients/base.py
"""Base class for audited clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.telemetry.events import ExternalCallCompleted

# Type alias for telemetry emit callback.
# When telemetry is disabled, orchestrator provides a no-op function.
# Clients always call this - never check for None.
TelemetryEmitCallback = Callable[["ExternalCallCompleted"], None]


class AuditedClientBase:
    """Base class for clients that automatically record to audit trail.

    Provides common infrastructure for tracking external calls:
    - Reference to LandscapeRecorder for audit storage and call index allocation
    - State ID linking calls to the current processing state
    - Run ID and telemetry callback for operational visibility

    Subclasses implement specific client protocols (LLM, HTTP, etc.)
    while inheriting automatic audit recording and telemetry emission.

    Thread Safety:
        The _next_call_index method delegates to LandscapeRecorder.allocate_call_index(),
        which is thread-safe. Multiple threads and multiple client types can safely
        call this method concurrently without risk of call_index collisions.

    Call Index Coordination:
        Call indices are allocated centrally by the LandscapeRecorder, ensuring
        UNIQUE(state_id, call_index) across all client types (HTTP, LLM) and retry
        attempts. This prevents IntegrityError when multiple clients share the same state_id.

    Telemetry:
        Clients emit ExternalCallCompleted events after successful Landscape recording.
        The telemetry_emit callback is always present - when telemetry is disabled,
        orchestrator provides a no-op. Clients never check for None.
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        state_id: str,
        run_id: str,
        telemetry_emit: TelemetryEmitCallback,
    ) -> None:
        """Initialize audited client.

        Args:
            recorder: LandscapeRecorder for audit trail storage and call index allocation
            state_id: Node state ID to associate calls with
            run_id: Pipeline run ID for telemetry correlation
            telemetry_emit: Callback to emit telemetry events (no-op when disabled)
        """
        self._recorder = recorder
        self._state_id = state_id
        self._run_id = run_id
        self._telemetry_emit = telemetry_emit

    def _next_call_index(self) -> int:
        """Get next call index for this state (thread-safe).

        Delegates to LandscapeRecorder for centralized call index allocation.
        This ensures unique indices across all client types sharing the same state_id.

        Returns:
            Sequential call index, unique within this state_id (not just this client)
        """
        return self._recorder.allocate_call_index(self._state_id)

    def close(self) -> None:
        """Release any resources held by the client.

        Default implementation is a no-op. Subclasses may override
        to close underlying connections or resources.
        """
        pass
