"""Row data retrieval types with explicit state discrimination.

Replaces the ambiguous `dict | None` return from get_row_data() with
explicit state handling. Callers can now match on state instead of
guessing why data is None.

States:
    AVAILABLE: Data was found and returned
    REPR_FALLBACK: Data was quarantined and stored as lossy repr snapshot
        (original contained non-canonical values like NaN/Infinity)
    PURGED: Data existed but was deleted (retention policy)
    NEVER_STORED: Row exists but source_data_ref was never set
    STORE_NOT_CONFIGURED: No payload store configured
    ROW_NOT_FOUND: Row ID doesn't exist in the database
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar

from elspeth.contracts.freeze import deep_freeze


class RowDataState(StrEnum):
    """Discriminator for row data retrieval results.

    Inherits from str for JSON serialization compatibility.
    """

    AVAILABLE = "available"
    REPR_FALLBACK = "repr_fallback"
    PURGED = "purged"
    NEVER_STORED = "never_stored"
    STORE_NOT_CONFIGURED = "store_not_configured"
    ROW_NOT_FOUND = "row_not_found"


@dataclass(frozen=True, slots=True)
class RowDataResult:
    """Result of a row data retrieval with explicit state.

    Invariants:
        - AVAILABLE and REPR_FALLBACK states require dict data
        - All other states require None data

    Example:
        result = recorder.get_row_data(row_id)
        match result.state:
            case RowDataState.AVAILABLE:
                process(result.data)  # Safe - guaranteed non-None
            case RowDataState.REPR_FALLBACK:
                log.warning("Data is lossy repr snapshot", data=result.data)
            case RowDataState.PURGED:
                log.info("Data was purged per retention policy")
            case RowDataState.ROW_NOT_FOUND:
                raise KeyError(f"Unknown row: {row_id}")
    """

    state: RowDataState
    data: Mapping[str, Any] | None

    _STATES_WITH_DATA: ClassVar[frozenset[RowDataState]] = frozenset({RowDataState.AVAILABLE, RowDataState.REPR_FALLBACK})

    def __post_init__(self) -> None:
        if type(self.state) is not RowDataState:
            raise TypeError(f"state must be RowDataState, got {type(self.state).__name__}")
        if self.state in self._STATES_WITH_DATA:
            if self.data is None:
                raise ValueError(f"{self.state} state requires non-None data")
            payload: object = self.data
            match payload:
                case dict() | MappingProxyType():
                    pass
                case _:
                    actual_type = type(payload).__name__
                    raise TypeError(f"{self.state} state requires dict data, got {actual_type}")
            if not isinstance(self.data, MappingProxyType):
                object.__setattr__(self, "data", deep_freeze(self.data))
        if self.state not in self._STATES_WITH_DATA and self.data is not None:
            raise ValueError(f"{self.state} state requires None data")
