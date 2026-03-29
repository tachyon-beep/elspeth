"""Reproducibility grade computation for completed pipeline runs.

This module computes and manages the reproducibility_grade field on the runs
table, which indicates how reliably a run can be reproduced or replayed.

Grades:
- FULL_REPRODUCIBLE: All nodes are deterministic or seeded. The run can be
  fully re-executed with identical results (given the same seed).
- REPLAY_REPRODUCIBLE: At least one node is nondeterministic (e.g., LLM calls).
  Results can only be replayed using recorded external call responses.
- ATTRIBUTABLE_ONLY: Payloads have been purged. We can verify what happened
  via hashes, but cannot replay the run.
"""

from typing import TYPE_CHECKING

from sqlalchemy import select

from elspeth.contracts import Determinism, ReproducibilityGrade
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.landscape.schema import nodes_table, runs_table

__all__ = [
    "ReproducibilityGrade",
    "compute_grade",
    "update_grade_after_purge",
]

if TYPE_CHECKING:
    from elspeth.core.landscape.database import LandscapeDB


def compute_grade(db: "LandscapeDB", run_id: str) -> ReproducibilityGrade:
    """Compute reproducibility grade from node determinism values.

    Logic:
    - If any node has non-reproducible determinism (EXTERNAL_CALL, NON_DETERMINISTIC,
      IO_READ, IO_WRITE), return REPLAY_REPRODUCIBLE
    - Otherwise return FULL_REPRODUCIBLE
    - Only DETERMINISTIC and SEEDED count as fully reproducible
    - Empty pipeline (no nodes) is trivially FULL_REPRODUCIBLE

    Args:
        db: LandscapeDB instance
        run_id: Run ID to compute grade for

    Returns:
        ReproducibilityGrade enum value

    Raises:
        AuditIntegrityError: If run does not exist or any node has invalid determinism value.
    """
    # Single connection for both queries — avoids TOCTOU window between
    # run existence check and node determinism fetch.
    with db.connection() as conn:
        # Verify run exists before computing grade — a nonexistent run_id
        # must not return FULL_REPRODUCIBLE (which is what "no nodes" implies).
        run_check = conn.execute(select(runs_table.c.run_id).where(runs_table.c.run_id == run_id))
        if run_check.fetchone() is None:
            raise AuditIntegrityError(f"Cannot compute reproducibility grade: run '{run_id}' does not exist")

        # Tier-1 audit data validation: Fetch ALL distinct determinism values
        # and validate each is a valid Determinism enum member.
        # Per Data Manifesto: "Bad data in the audit trail = crash immediately"
        query_all = select(nodes_table.c.determinism).where(nodes_table.c.run_id == run_id).distinct()
        result = conn.execute(query_all)
        raw_values = [row[0] for row in result.fetchall()]

    # Validate all determinism values and convert to enum members
    determinism_values: list[Determinism] = []
    for det_value in raw_values:
        if det_value is None:
            raise AuditIntegrityError(f"NULL determinism value in nodes table for run {run_id} — audit data corruption")
        try:
            determinism_values.append(Determinism(det_value))
        except ValueError as exc:
            raise AuditIntegrityError(
                f"Invalid determinism value '{det_value}' in nodes table for run {run_id} — "
                f"expected one of {[d.value for d in Determinism]}"
            ) from exc

    # Determinism values that require replay (cannot reproduce from inputs alone)
    # IO_READ/IO_WRITE are external/side-effectful - require captured data for replay
    non_reproducible = {
        Determinism.EXTERNAL_CALL,
        Determinism.NON_DETERMINISTIC,
        Determinism.IO_READ,
        Determinism.IO_WRITE,
    }

    # Check if any non-reproducible determinism values exist — both sides
    # are now Determinism enum members, no implicit StrEnum comparison.
    has_non_reproducible = any(det in non_reproducible for det in determinism_values)

    if has_non_reproducible:
        return ReproducibilityGrade.REPLAY_REPRODUCIBLE
    else:
        return ReproducibilityGrade.FULL_REPRODUCIBLE


def update_grade_after_purge(db: "LandscapeDB", run_id: str) -> None:
    """Degrade reproducibility grade after payload purge.

    After payloads are purged, nondeterministic runs can no longer be
    replayed (we don't have the recorded responses). The grade degrades:
    - REPLAY_REPRODUCIBLE -> ATTRIBUTABLE_ONLY
    - FULL_REPRODUCIBLE -> unchanged (doesn't depend on payloads)
    - ATTRIBUTABLE_ONLY -> unchanged (already at lowest grade)

    Args:
        db: LandscapeDB instance
        run_id: Run ID to potentially degrade
    """
    with db.connection() as conn:
        # Tier 1 validation: verify audit data integrity before mutation
        query = select(runs_table.c.reproducibility_grade).where(runs_table.c.run_id == run_id)
        result = conn.execute(query)
        row = result.fetchone()

        if row is None:
            raise AuditIntegrityError(f"Cannot update reproducibility grade after purge: run '{run_id}' does not exist")

        current_grade = row[0]

        # Per Data Manifesto: "Bad data in the audit trail = crash immediately"
        if current_grade is None:
            raise AuditIntegrityError(f"NULL reproducibility_grade for run {run_id} — audit data corruption")

        try:
            ReproducibilityGrade(current_grade)
        except ValueError as exc:
            raise AuditIntegrityError(
                f"Invalid reproducibility_grade '{current_grade}' for run {run_id} — "
                f"expected one of {[g.value for g in ReproducibilityGrade]}"
            ) from exc

        # Atomic conditional update — no read-modify-write race.
        # The WHERE clause acts as a compare-and-swap: only degrades if still REPLAY_REPRODUCIBLE.
        conn.execute(
            runs_table.update()
            .where(runs_table.c.run_id == run_id)
            .where(runs_table.c.reproducibility_grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE)
            .values(reproducibility_grade=ReproducibilityGrade.ATTRIBUTABLE_ONLY)
        )
