"""Pipeline run result — pure data type for pipeline execution outcomes.

Moved to L0 (contracts/) because it has no dependencies above L0: uses only
RunStatus (L0), freeze_fields (L0), and stdlib types. This placement allows
PipelineRunner protocol (also L0) to reference it without a layer violation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from elspeth.contracts.enums import RunStatus
from elspeth.contracts.freeze import freeze_fields


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
    routed_destinations: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        freeze_fields(self, "routed_destinations")
