"""Utilities for neutralising spreadsheet formula injection primitives."""

from __future__ import annotations

from typing import Any

# Characters that can trigger formula evaluation when placed at the start of a cell.
DANGEROUS_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n", "'")
_BOM = "\ufeff"


def _normalize_guard(guard: str | None) -> str:
    guard = guard or "'"
    if len(guard) != 1:
        raise ValueError("sanitize guard must be a single character")
    return guard


def _split_bom(value: str) -> tuple[str, str]:
    if value.startswith(_BOM):
        # Excel tolerates the UTF-8 BOM prefix; retain it to avoid surprises downstream.
        return _BOM, value[len(_BOM) :]
    return "", value


def should_sanitize(value: Any, *, guard: str | None = "'", aggressive: bool = False) -> bool:
    """Return True when the provided value should be prefixed with the guard."""

    if not isinstance(value, str) or value == "":
        return False
    guard_char = _normalize_guard(guard)
    bom, remainder = _split_bom(value)
    if not remainder:
        return False
    if not aggressive and remainder.startswith(guard_char):
        return False
    return remainder[0] in DANGEROUS_PREFIXES


def sanitize_cell(value: Any, *, guard: str | None = "'", aggressive: bool = False) -> Any:
    """Return a sanitised value suitable for CSV/Excel output."""

    if not isinstance(value, str) or value == "":
        return value
    guard_char = _normalize_guard(guard)
    bom, remainder = _split_bom(value)
    if not remainder:
        return value
    if not aggressive and remainder.startswith(guard_char):
        return value
    if remainder[0] in DANGEROUS_PREFIXES:
        return f"{bom}{guard_char}{remainder}"
    return value


__all__ = ["sanitize_cell", "should_sanitize", "DANGEROUS_PREFIXES"]
