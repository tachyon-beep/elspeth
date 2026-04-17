"""Helpers for ConfigParser-backed Alembic configuration."""

from __future__ import annotations


def escape_alembic_config_value(value: str) -> str:
    """Escape percent signs before writing values into Alembic Config.

    Alembic stores options in ``ConfigParser``, where ``%`` starts an
    interpolation sequence. ``Config.get_main_option()`` returns the
    original value again, so callers should escape only on write.
    """
    return value.replace("%", "%%")
