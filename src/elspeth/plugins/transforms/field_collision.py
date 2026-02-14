"""Field collision detection for transforms.

Transforms that enrich rows with new fields must check for collisions
with existing input fields before writing. Silent overwrites are data loss.
"""

from __future__ import annotations

from collections.abc import Iterable


def detect_field_collisions(
    existing_fields: set[str],
    new_fields: Iterable[str],
) -> list[str] | None:
    """Detect field name collisions between existing row fields and new fields.

    Args:
        existing_fields: Field names already present in the row.
        new_fields: Field names the transform intends to add.

    Returns:
        Sorted list of colliding field names, or None if no collisions.
    """
    collisions = sorted(f for f in new_fields if f in existing_fields)
    return collisions or None
