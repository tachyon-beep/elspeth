"""Landscape-specific recorder error taxonomy.

Separate durable audit-write failures from ordinary programmer bugs so
callers can add context without masking unrelated exceptions.
"""

from __future__ import annotations

from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.tier_registry import tier_1_error


@tier_1_error(
    reason="ADR-010: narrow recorder failure marker for durable audit write/materialization faults",
    caller_module=__name__,
)
class LandscapeRecordError(AuditIntegrityError):
    """Recorder failed to durably write or materialize audit evidence.

    This remains a Tier-1 audit failure via ``AuditIntegrityError`` but
    gives higher layers a narrow marker they can catch without also
    swallowing arbitrary ``ValueError``/``RuntimeError`` bugs.
    """
