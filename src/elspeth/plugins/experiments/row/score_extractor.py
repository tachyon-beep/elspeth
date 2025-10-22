"""Score Extractor - Extract numeric scores from LLM responses."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.experiments.plugin_registry import register_row_plugin
from elspeth.plugins.experiments._stats_helpers import _create_score_extractor_factory

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": "Field name to extract score from (required)",
        },
        "criteria": {"type": "array", "items": {"type": "string"}},
        "parse_json_content": {
            "type": "boolean",
            "description": "Parse JSON content to extract scores (required)",
        },
        "allow_missing": {
            "type": "boolean",
            "description": "Allow missing score fields (required)",
        },
        "threshold": {"type": "number"},
        "threshold_mode": {
            "type": "string",
            "enum": ["gt", "gte", "lt", "lte"],
            "description": "Threshold comparison mode (required)",
        },
        "flag_field": {
            "type": "string",
            "description": "Field name for threshold flags (required)",
        },
    },
    "additionalProperties": True,
}


class ScoreExtractorPlugin:
    """Extract numeric scores from LLM responses.

    The plugin inspects the per-criteria response payload for numeric values under
    the configured key (default: ``score``). Values are normalised to ``float``
    whenever possible. When ``threshold`` is supplied the plugin also flags rows
    that meet the threshold for downstream aggregators.
    """

    name = "score_extractor"

    def __init__(
        self,
        *,
        key: str = "score",
        criteria: list[str] | None = None,
        parse_json_content: bool = True,
        allow_missing: bool = False,
        threshold: float | None = None,
        threshold_mode: str = "gte",
        flag_field: str = "score_flags",
    ) -> None:
        self._key = key
        self._criteria = set(criteria) if criteria else None
        self._parse_json = parse_json_content
        self._allow_missing = allow_missing
        self._threshold = threshold
        self._threshold_mode = threshold_mode
        self._flag_field = flag_field

    def process_row(self, _row: dict[str, Any], responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """Extract per-criteria scores and optional threshold flags from responses.

        Args:
            _row: The original input row (unused by this plugin but part of the interface)
            responses: Mapping of criterion name -> response payload

        Returns:
            A derived dictionary containing optional keys: "scores" and the configured
            flag field (defaults to "score_flags"). Empty when neither are present.
        """
        scores: dict[str, float] = {}
        flags: dict[str, bool] = {}

        for crit_name, response in responses.items():
            criteria = self._criteria
            if criteria is not None and crit_name not in criteria:
                continue
            value = self._extract_value(response)
            if value is None:
                if not self._allow_missing:
                    scores[crit_name] = np.nan
                continue
            scores[crit_name] = value
            if self._threshold is not None:
                flags[crit_name] = self._compare_threshold(value)

        derived: dict[str, Any] = {}
        if scores:
            derived.setdefault("scores", {}).update(scores)
        if flags:
            derived[self._flag_field] = flags
        return derived

    def _extract_value(self, response: Mapping[str, Any]) -> float | None:
        metrics = response.get("metrics") if isinstance(response, Mapping) else None
        if isinstance(metrics, Mapping) and self._key in metrics:
            return self._coerce_number(metrics.get(self._key))

        if self._parse_json:
            content = response.get("content") if isinstance(response, Mapping) else None
            if isinstance(content, str):
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, Mapping) and self._key in payload:
                    return self._coerce_number(payload.get(self._key))
        return None

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.endswith("%"):
                cleaned = cleaned[:-1]
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    def _compare_threshold(self, value: float) -> bool:
        if self._threshold is None:  # pragma: no cover - defensive
            raise RuntimeError(
                "ScoreExtractorPlugin._compare_threshold: score threshold must be configured before comparison (self._threshold is None)"
            )
        mode = self._threshold_mode
        threshold = float(self._threshold)
        if mode == "gt":
            return value > threshold
        if mode == "gte":
            return value >= threshold
        if mode == "lt":
            return value < threshold
        if mode == "lte":
            return value <= threshold
        raise ValueError(f"Unsupported threshold_mode '{mode}'")

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """ScoreExtractorPlugin does not require specific input columns."""
        return None


def _create_score_extractor(options: dict[str, Any], _context: PluginContext) -> ScoreExtractorPlugin:
    """Create a score extractor plugin with all required fields."""
    validated = _create_score_extractor_factory(options)
    return ScoreExtractorPlugin(**validated)


register_row_plugin(
    "score_extractor",
    _create_score_extractor,
    schema=_ROW_SCHEMA,
)


__all__ = ["ScoreExtractorPlugin"]
