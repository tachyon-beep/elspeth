"""Sink diversion contracts — per-row write failure routing types.

These types support the failsink pattern: when a sink can't write a specific
row (value-level failure at the Tier 2 -> External boundary), it diverts the
row to a failsink. These contracts carry diversion information from the plugin's
write() method back to SinkExecutor for audit trail recording.

Layer: L0 (contracts). Imports only from L0 and stdlib.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from elspeth.contracts.freeze import freeze_fields, require_int
from elspeth.contracts.results import ArtifactDescriptor


@dataclass(frozen=True, slots=True)
class RowDiversion:
    """Record of a single row diverted to failsink during write().

    Created by BaseSink._divert_row() and accumulated in _diversion_log.
    Read by SinkExecutor after write() returns to record per-token outcomes.

    Attributes:
        row_index: Index in the original batch passed to write().
        reason: Why the external system rejected this row.
        row_data: The row that was diverted (for failsink write).
    """

    row_index: int
    reason: str
    row_data: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_int(self.row_index, "row_index", min_value=0)
        freeze_fields(self, "row_data")


@dataclass(frozen=True, slots=True)
class SinkWriteResult:
    """Result of a sink write() call with optional diversion information.

    Replaces ArtifactDescriptor as the return type of BaseSink.write().
    Sinks with no diversions return SinkWriteResult(artifact=..., diversions=()).

    Attributes:
        artifact: ArtifactDescriptor for the primary write (may represent zero rows
            if all were diverted).
        diversions: Tuple of RowDiversion records for rows diverted during write().
            Empty tuple if no diversions occurred.
    """

    artifact: ArtifactDescriptor
    diversions: tuple[RowDiversion, ...] = ()
