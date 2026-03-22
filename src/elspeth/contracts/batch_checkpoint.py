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
from typing import Any

from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.freeze import deep_freeze, deep_thaw


@dataclass(frozen=True, slots=True)
class RowMappingEntry:
    """Checkpoint-serializable mapping from custom_id to row index + hash.

    Used by Azure Batch transforms to map API response custom_ids back to
    the original row positions in the batch.
    """

    index: int
    variables_hash: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"RowMappingEntry.index must be non-negative, got {self.index}")
        if not self.variables_hash:
            raise ValueError("RowMappingEntry.variables_hash must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "variables_hash": self.variables_hash}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RowMappingEntry:
        """Deserialize from checkpoint JSON.

        This is Tier 1 data — crash on any structural anomaly.
        """
        required_fields = {"index", "variables_hash"}
        missing = required_fields - set(data.keys())
        if missing:
            raise AuditIntegrityError(f"Corrupted RowMappingEntry checkpoint: missing required fields {missing}. Found: {set(data.keys())}")
        index = data["index"]
        if not isinstance(index, int):
            raise AuditIntegrityError(f"Corrupted RowMappingEntry checkpoint: 'index' must be int, got {type(index).__name__}: {index!r}")
        return cls(index=index, variables_hash=data["variables_hash"])


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
        if not self.batch_id:
            raise ValueError("BatchCheckpointState.batch_id must not be empty")
        if not self.input_file_id:
            raise ValueError("BatchCheckpointState.input_file_id must not be empty")
        if not self.submitted_at:
            raise ValueError("BatchCheckpointState.submitted_at must not be empty")
        if self.row_count < 0:
            raise ValueError(f"BatchCheckpointState.row_count must be non-negative, got {self.row_count}")
        frozen_mapping = deep_freeze(self.row_mapping)
        if frozen_mapping is not self.row_mapping:
            object.__setattr__(self, "row_mapping", frozen_mapping)
        frozen_errors = deep_freeze(self.template_errors)
        if frozen_errors is not self.template_errors:
            object.__setattr__(self, "template_errors", frozen_errors)
        for i, entry in enumerate(self.template_errors):
            if len(entry) != 2:
                raise ValueError(f"BatchCheckpointState.template_errors[{i}] must be (int, str), got {len(entry)}-element tuple: {entry!r}")
            idx, msg = entry
            if not isinstance(idx, int):
                raise ValueError(f"BatchCheckpointState.template_errors[{i}][0] must be int, got {type(idx).__name__}: {idx!r}")
            if not isinstance(msg, str):
                raise ValueError(f"BatchCheckpointState.template_errors[{i}][1] must be str, got {type(msg).__name__}: {msg!r}")
        frozen_requests = deep_freeze(self.requests)
        if frozen_requests is not self.requests:
            object.__setattr__(self, "requests", frozen_requests)

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
        required_fields = {
            "batch_id",
            "input_file_id",
            "row_mapping",
            "template_errors",
            "submitted_at",
            "row_count",
            "requests",
        }
        missing = required_fields - set(data.keys())
        if missing:
            raise AuditIntegrityError(f"Corrupted batch checkpoint: missing required fields {missing}. Found: {set(data.keys())}")
        row_mapping = data["row_mapping"]
        if not isinstance(row_mapping, dict):
            raise AuditIntegrityError(
                f"Corrupted batch checkpoint: 'row_mapping' must be a dict, got {type(row_mapping).__name__}: {row_mapping!r}"
            )

        requests = data["requests"]
        if not isinstance(requests, dict):
            raise AuditIntegrityError(f"Corrupted batch checkpoint: 'requests' must be a dict, got {type(requests).__name__}: {requests!r}")

        raw_errors = data["template_errors"]
        template_errors: list[tuple[int, str]] = []
        for i, entry in enumerate(raw_errors):
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise AuditIntegrityError(
                    f"Corrupted batch checkpoint: template_errors[{i}] must be a 2-element [int, str], "
                    f"got {type(entry).__name__}: {entry!r}"
                )
            idx, msg = entry
            if not isinstance(idx, int):
                raise AuditIntegrityError(
                    f"Corrupted batch checkpoint: template_errors[{i}][0] must be int, got {type(idx).__name__}: {idx!r}"
                )
            if not isinstance(msg, str):
                raise AuditIntegrityError(
                    f"Corrupted batch checkpoint: template_errors[{i}][1] must be str, got {type(msg).__name__}: {msg!r}"
                )
            template_errors.append((idx, msg))

        return cls(
            batch_id=data["batch_id"],
            input_file_id=data["input_file_id"],
            row_mapping={k: RowMappingEntry.from_dict(v) for k, v in row_mapping.items()},
            template_errors=tuple(template_errors),
            submitted_at=data["submitted_at"],
            row_count=data["row_count"],
            requests=requests,
        )
