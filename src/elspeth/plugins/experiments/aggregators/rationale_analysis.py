"""RationaleAnalysisAggregator - Aggregation plugin."""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_RATIONALE_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale_field": {"type": "string"},
        "score_field": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_word_length": {"type": "integer", "minimum": 2},
        "top_keywords": {"type": "integer", "minimum": 1},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class RationaleAnalysisAggregator:
    """Analyze LLM rationales to understand scoring patterns and provide interpretability.

    This plugin extracts rationales from response content, analyzes common themes
    in low vs high scoring responses, computes rationale length statistics, and
    identifies confidence indicators. Provides qualitative insights to complement
    quantitative scoring metrics.
    """

    name = "rationale_analysis"

    def __init__(
        self,
        *,
        rationale_field: str = "rationale",
        score_field: str = "score",
        criteria: list[str] | None = None,
        min_word_length: int = 3,
        top_keywords: int = 10,
        on_error: str = "abort",
    ) -> None:
        self._rationale_field = rationale_field
        self._score_field = score_field
        self._criteria = set(criteria) if criteria else None
        self._min_word_length = max(int(min_word_length), 2)
        self._top_keywords = max(int(top_keywords), 1)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

        # Common stop words to filter out
        self._stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "this",
            "that",
            "these",
            "those",
            "it",
            "as",
            "not",
        }

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("rationale_analysis skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}

        # Collect rationales and scores by criterion
        criterion_data: dict[str, dict[str, Any]] = {}

        for record in records:
            responses = record.get("responses") or {}
            metrics = record.get("metrics") or {}
            scores = metrics.get("scores") or {}

            for crit_name, response in responses.items():
                if self._criteria and crit_name not in self._criteria:
                    continue

                # Extract rationale from response content
                rationale = self._extract_rationale(response)
                if not rationale:
                    continue

                # Extract score
                score = scores.get(crit_name)
                if score is None:
                    continue
                try:
                    score_val = float(score)
                except (TypeError, ValueError):
                    continue
                if math.isnan(score_val):
                    continue

                # Store in criterion bucket
                bucket = criterion_data.setdefault(
                    crit_name,
                    {
                        "rationales": [],
                        "scores": [],
                        "low_score_words": [],
                        "high_score_words": [],
                    },
                )
                bucket["rationales"].append(rationale)
                bucket["scores"].append(score_val)

                # Categorize words by score
                words = self._extract_words(rationale)
                if score_val <= 2:
                    bucket["low_score_words"].extend(words)
                elif score_val >= 4:
                    bucket["high_score_words"].extend(words)

        # Analyze each criterion
        results: dict[str, Any] = {}
        overall_stats: dict[str, Any] = {
            "total_rationales": 0,
            "avg_length_chars": 0.0,
            "avg_length_words": 0.0,
        }

        all_lengths_chars = []
        all_lengths_words = []

        for crit_name, data in criterion_data.items():
            rationales = data["rationales"]
            scores = data["scores"]

            if not rationales:
                continue

            # Length statistics
            lengths_chars = [len(r) for r in rationales]
            lengths_words = [len(r.split()) for r in rationales]
            all_lengths_chars.extend(lengths_chars)
            all_lengths_words.extend(lengths_words)

            # Keyword analysis

            low_counter = Counter(data["low_score_words"])
            high_counter = Counter(data["high_score_words"])

            low_keywords = [{"word": word, "count": count} for word, count in low_counter.most_common(self._top_keywords)]
            high_keywords = [{"word": word, "count": count} for word, count in high_counter.most_common(self._top_keywords)]

            # Confidence indicators (simple heuristic)
            confidence_indicators = self._detect_confidence(rationales)

            # Score correlation with length
            length_score_corr = None
            if len(lengths_chars) >= 2:
                try:
                    corr_arr = np.corrcoef(lengths_chars, scores)
                    length_score_corr = float(corr_arr[0, 1]) if not np.isnan(corr_arr[0, 1]) else None
                except Exception:  # pragma: no cover
                    length_score_corr = None

            results[crit_name] = {
                "count": len(rationales),
                "avg_length_chars": float(np.mean(lengths_chars)),
                "avg_length_words": float(np.mean(lengths_words)),
                "min_length_chars": min(lengths_chars),
                "max_length_chars": max(lengths_chars),
                "length_score_correlation": length_score_corr,
                "low_score_keywords": low_keywords,
                "high_score_keywords": high_keywords,
                "confidence_indicators": confidence_indicators,
            }

        # Overall statistics
        if all_lengths_chars:
            overall_stats["total_rationales"] = len(all_lengths_chars)
            overall_stats["avg_length_chars"] = float(np.mean(all_lengths_chars))
            overall_stats["avg_length_words"] = float(np.mean(all_lengths_words))
            overall_stats["median_length_chars"] = float(np.median(all_lengths_chars))
            overall_stats["median_length_words"] = float(np.median(all_lengths_words))

        return {
            "criteria": results,
            "overall": overall_stats,
        }

    def _extract_rationale(self, response: Mapping[str, Any]) -> str | None:
        """Extract rationale text from response content."""
        # Try metrics first
        metrics = response.get("metrics")
        if isinstance(metrics, Mapping) and self._rationale_field in metrics:
            rationale = metrics.get(self._rationale_field)
            if isinstance(rationale, str) and rationale.strip():
                return rationale.strip()

        # Try parsing JSON content
        content = response.get("content")
        if isinstance(content, str):
            try:
                payload = json.loads(content)
                if isinstance(payload, Mapping) and self._rationale_field in payload:
                    rationale = payload.get(self._rationale_field)
                    if isinstance(rationale, str) and rationale.strip():
                        return rationale.strip()
            except json.JSONDecodeError:
                pass

        return None

    def _extract_words(self, text: str) -> list[str]:
        """Extract meaningful words from text, filtering stop words and short words."""
        import re

        words = re.findall(r"\b\w+\b", text.lower())
        return [w for w in words if len(w) >= self._min_word_length and w not in self._stop_words]

    def _detect_confidence(self, rationales: list[str]) -> dict[str, Any]:
        """Detect confidence indicators in rationales (simple heuristic)."""
        high_confidence_words = {"clearly", "definitely", "certainly", "obviously", "absolutely", "undoubtedly"}
        low_confidence_words = {"maybe", "perhaps", "possibly", "might", "somewhat", "unclear", "uncertain"}
        hedge_words = {"seems", "appears", "suggests", "likely", "probably", "potentially"}

        high_conf_count = 0
        low_conf_count = 0
        hedge_count = 0

        for rationale in rationales:
            text_lower = rationale.lower()
            if any(word in text_lower for word in high_confidence_words):
                high_conf_count += 1
            if any(word in text_lower for word in low_confidence_words):
                low_conf_count += 1
            if any(word in text_lower for word in hedge_words):
                hedge_count += 1

        total = len(rationales)
        return {
            "high_confidence_rate": high_conf_count / total if total else 0.0,
            "low_confidence_rate": low_conf_count / total if total else 0.0,
            "hedge_rate": hedge_count / total if total else 0.0,
        }

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """RationaleAnalysisAggregator does not require specific input columns."""
        return None


register_aggregation_plugin(
    "rationale_analysis",
    lambda options, context: RationaleAnalysisAggregator(
        rationale_field=options.get("rationale_field", "rationale"),
        score_field=options.get("score_field", "score"),
        criteria=options.get("criteria"),
        min_word_length=int(options.get("min_word_length", 3)),
        top_keywords=int(options.get("top_keywords", 10)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_RATIONALE_SCHEMA,
)


__all__ = ["RationaleAnalysisAggregator"]
