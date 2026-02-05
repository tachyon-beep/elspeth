"""Database operation helpers to reduce boilerplate in recorder.

Consolidates the repeated `with self._db.connection() as conn:` pattern.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Executable
from sqlalchemy.engine import Row

if TYPE_CHECKING:
    from elspeth.core.landscape.database import LandscapeDB


class DatabaseOps:
    """Helper for common database operations.

    Reduces boilerplate in recorder methods by centralizing
    connection management.
    """

    def __init__(self, db: "LandscapeDB") -> None:
        self._db = db

    def execute_fetchone(self, query: Executable) -> Row[Any] | None:
        """Execute query and return single row or None."""
        with self._db.connection() as conn:
            result = conn.execute(query)
            return result.fetchone()

    def execute_fetchall(self, query: Executable) -> list[Row[Any]]:
        """Execute query and return all rows."""
        with self._db.connection() as conn:
            result = conn.execute(query)
            return list(result.fetchall())

    def execute_insert(self, stmt: Executable) -> None:
        """Execute insert statement.

        Raises:
            ValueError: If zero rows are affected (Tier-1 audit integrity violation)
        """
        with self._db.connection() as conn:
            result = conn.execute(stmt)
            if result.rowcount == 0:
                raise ValueError("execute_insert: zero rows affected - audit write failed (missing parent row or constraint violation)")

    def execute_update(self, stmt: Executable) -> None:
        """Execute update statement.

        Raises:
            ValueError: If zero rows are affected (Tier-1 audit integrity violation)
        """
        with self._db.connection() as conn:
            result = conn.execute(stmt)
            if result.rowcount == 0:
                raise ValueError("execute_update: zero rows affected - target row does not exist (audit data corruption)")
