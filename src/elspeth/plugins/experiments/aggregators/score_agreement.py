"""ScoreAgreementAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np
import pingouin

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_AGREEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_items": {"type": "integer", "minimum": 2},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreAgreementAggregator:
    """Assess agreement/reliability across criteria scores."""

    name = "score_agreement"

    def __init__(self, *, criteria: Sequence[str] | None = None, min_items: int = 2, on_error: str = "abort") -> None:
        self._criteria = list(criteria) if criteria else None
        self._min_items = max(int(min_items), 2)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("score_agreement skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}

        matrix: dict[str, list[float]] = {}
        for record in records:
            metrics = record.get("metrics") or {}
            scores = metrics.get("scores") or {}
            if not isinstance(scores, Mapping):
                continue
            for name, value in scores.items():
                if self._criteria and name not in self._criteria:
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isnan(number):
                    continue
                matrix.setdefault(name, []).append(number)

        usable = {name: values for name, values in matrix.items() if len(values) >= self._min_items}
        if len(usable) < 2:
            return {}

        columns = sorted(usable.keys())
        lengths = [len(usable[name]) for name in columns]
        max_len = max(lengths)
        data = []
        for idx in range(max_len):
            row = []
            for name in columns:
                values = usable[name]
                row.append(values[idx] if idx < len(values) else np.nan)
            data.append(row)
        arr = np.array(data, dtype=float)

        mask = ~np.isnan(arr).all(axis=1)
        arr = arr[mask]
        if arr.shape[0] < self._min_items:
            return {}

        item_variances = np.nanvar(arr, axis=0, ddof=1)
        total_variance = np.nanvar(arr, ddof=1)
        n_items = arr.shape[1]
        if total_variance <= 0 or n_items < 2 or np.isnan(total_variance):
            cronbach_alpha = None
        else:
            cronbach_alpha = (n_items / (n_items - 1)) * (1 - np.nansum(item_variances) / total_variance)

        correlations = []
        for i in range(n_items):
            for j in range(i + 1, n_items):
                col_i = arr[:, i]
                col_j = arr[:, j]
                valid = ~np.isnan(col_i) & ~np.isnan(col_j)
                if valid.sum() >= 2:
                    corr = np.corrcoef(col_i[valid], col_j[valid])[0, 1]
                    if not np.isnan(corr):
                        correlations.append(corr)
        avg_correlation = float(np.mean(correlations)) if correlations else None

        krippendorff_alpha = None
        if pingouin is not None and arr.shape[1] >= 2:
            try:
                import pandas as pd

                df = pd.DataFrame({columns[i]: arr[:, i] for i in range(n_items)})
                krippendorff_alpha = float(pingouin.krippendorff_alpha(df, reliability_data=True))
            except Exception:  # pragma: no cover - pingouin failure
                krippendorff_alpha = None

        return {
            "criteria": columns,
            "cronbach_alpha": cronbach_alpha,
            "average_correlation": avg_correlation,
            "krippendorff_alpha": krippendorff_alpha,
        }

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """ScoreAgreementAggregator does not require specific input columns."""
        return None


register_aggregation_plugin(
    "score_agreement",
    lambda options, context: ScoreAgreementAggregator(
        criteria=options.get("criteria"),
        min_items=int(options.get("min_items", 2)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_AGREEMENT_SCHEMA,
)


__all__ = ["ScoreAgreementAggregator"]
