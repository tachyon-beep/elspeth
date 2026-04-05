"""Pipeline run result — pure data type for pipeline execution outcomes.

Moved to L0 (contracts/) because it has no dependencies above L0: uses only
RunStatus (L0), freeze_fields (L0), and stdlib types. This placement allows
PipelineRunner protocol (also L0) to reference it without a layer violation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from elspeth.contracts.enums import RunStatus
from elspeth.contracts.freeze import deep_thaw, freeze_fields, require_int


@dataclass(frozen=True, slots=True)
class RunResult:
    """Result of a pipeline run."""

    run_id: str
    status: RunStatus
    rows_processed: int
    rows_succeeded: int
    rows_failed: int
    rows_routed: int
    rows_quarantined: int = 0
    rows_forked: int = 0
    rows_coalesced: int = 0
    rows_coalesce_failed: int = 0  # Coalesce failures (quorum_not_met, incomplete_branches)
    rows_expanded: int = 0  # Deaggregation parent tokens
    rows_buffered: int = 0  # Passthrough mode buffered tokens
    rows_diverted: int = 0  # Rows diverted to failsink during sink write
    routed_destinations: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id must not be empty")
        if not isinstance(self.status, RunStatus):
            raise TypeError(f"RunResult.status must be a RunStatus enum, got {type(self.status).__name__}: {self.status!r}")
        require_int(self.rows_processed, "rows_processed", min_value=0)
        require_int(self.rows_succeeded, "rows_succeeded", min_value=0)
        require_int(self.rows_failed, "rows_failed", min_value=0)
        require_int(self.rows_routed, "rows_routed", min_value=0)
        require_int(self.rows_quarantined, "rows_quarantined", min_value=0)
        require_int(self.rows_forked, "rows_forked", min_value=0)
        require_int(self.rows_coalesced, "rows_coalesced", min_value=0)
        require_int(self.rows_coalesce_failed, "rows_coalesce_failed", min_value=0)
        require_int(self.rows_expanded, "rows_expanded", min_value=0)
        require_int(self.rows_buffered, "rows_buffered", min_value=0)
        require_int(self.rows_diverted, "rows_diverted", min_value=0)
        freeze_fields(self, "routed_destinations")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export.

        Replaces ``dataclasses.asdict()`` which cannot deep-copy
        ``MappingProxyType`` fields (raises ``TypeError: cannot pickle
        'mappingproxy' object``).
        """
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "rows_processed": self.rows_processed,
            "rows_succeeded": self.rows_succeeded,
            "rows_failed": self.rows_failed,
            "rows_routed": self.rows_routed,
            "rows_quarantined": self.rows_quarantined,
            "rows_forked": self.rows_forked,
            "rows_coalesced": self.rows_coalesced,
            "rows_coalesce_failed": self.rows_coalesce_failed,
            "rows_expanded": self.rows_expanded,
            "rows_buffered": self.rows_buffered,
            "rows_diverted": self.rows_diverted,
            "routed_destinations": deep_thaw(self.routed_destinations),
        }
