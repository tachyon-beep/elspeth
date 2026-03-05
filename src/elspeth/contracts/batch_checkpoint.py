"""Typed batch checkpoint state for Azure Batch LLM transforms.

Replaces the untyped dict[str, Any] that previously flowed through
PluginContext, BatchPendingError, and the checkpoint persistence layer.

This is Tier 1 data (we wrote it). Deserialization crashes on missing
or wrong-typed fields — corruption in our checkpoint DB is a crash,
not a data quality issue to handle gracefully.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from elspeth.contracts.freeze import deep_freeze, deep_thaw


@dataclass(frozen=True, slots=True)
class RowMappingEntry:
    """Checkpoint-serializable mapping from custom_id to row index + hash.

    Used by Azure Batch transforms to map API response custom_ids back to
    the original row positions in the batch.
    """

    index: int
    variables_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "variables_hash": self.variables_hash}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RowMappingEntry:
        """Deserialize from checkpoint JSON.

        This is Tier 1 data — crash on any structural anomaly.
        """
        return cls(index=data["index"], variables_hash=data["variables_hash"])


@dataclass(frozen=True, slots=True)
class BatchCheckpointState:
    """Typed checkpoint state for batch LLM transforms.

    Captures the full state needed to resume a batch after
    BatchPendingError: the Azure batch ID, input file, row mapping,
    and original requests for audit recording.

    Attributes:
        batch_id: Azure batch job ID
        input_file_id: Azure file ID for uploaded input
        row_mapping: Maps custom_id to RowMappingEntry (row index + hash)
        template_errors: List of (row_index, error_message) for failed renders
        submitted_at: ISO datetime string of batch submission
        row_count: Number of rows in the batch
        requests: Original API requests by custom_id (for audit recording)
    """

    batch_id: str
    input_file_id: str
    row_mapping: Mapping[str, RowMappingEntry]
    template_errors: Sequence[tuple[int, str]]
    submitted_at: str
    row_count: int
    requests: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        if not isinstance(self.row_mapping, MappingProxyType):
            object.__setattr__(self, "row_mapping", MappingProxyType(self.row_mapping))
        if not isinstance(self.template_errors, tuple):
            object.__setattr__(self, "template_errors", tuple(self.template_errors))
        if not isinstance(self.requests, MappingProxyType):
            object.__setattr__(self, "requests", deep_freeze(self.requests))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON checkpoint persistence.

        Wire-compatible with the previous untyped dict format.
        """
        return {
            "batch_id": self.batch_id,
            "input_file_id": self.input_file_id,
            "row_mapping": {k: v.to_dict() for k, v in self.row_mapping.items()},
            "template_errors": [list(te) for te in self.template_errors],
            "submitted_at": self.submitted_at,
            "row_count": self.row_count,
            "requests": deep_thaw(self.requests),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchCheckpointState:
        """Deserialize from checkpoint JSON.

        This is Tier 1 data (we wrote the checkpoint). Crash on any
        structural anomaly — missing keys or wrong types indicate
        checkpoint corruption, not a data quality issue.
        """
        return cls(
            batch_id=data["batch_id"],
            input_file_id=data["input_file_id"],
            row_mapping={k: RowMappingEntry.from_dict(v) for k, v in data["row_mapping"].items()},
            template_errors=tuple((int(idx), str(msg)) for idx, msg in data["template_errors"]),
            submitted_at=data["submitted_at"],
            row_count=data["row_count"],
            requests=data["requests"],
        )
