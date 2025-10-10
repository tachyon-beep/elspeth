"""Data preparation helpers for experiment prompts."""

from __future__ import annotations

from typing import Any, Dict, Iterable

import pandas as pd


def prepare_prompt_context(
    row: pd.Series,
    *,
    include_fields: Iterable[str] | None = None,
    alias_map: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Extract a lightweight context dictionary from a dataframe row.

    Parameters
    ----------
    row:
        The pandas Series representing a single experiment record.
    include_fields:
        Optional iterable restricting which columns are surfaced. When omitted
        the full row is used.
    alias_map:
        Optional mapping from column name to alternate key name in the
        resulting context.
    """

    data = row.to_dict()
    if include_fields is not None:
        data = {key: data.get(key) for key in include_fields}

    if alias_map:
        for column, alias in alias_map.items():
            if column in data:
                data[alias] = data.pop(column)

    return data
