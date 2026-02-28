"""Common helper functions for landscape modules.

These are extracted from recorder.py to be shared across landscape modules.
"""

import uuid
from datetime import UTC, datetime


def now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)


def generate_id() -> str:
    """Generate a unique ID (UUID4 hex)."""
    return uuid.uuid4().hex
