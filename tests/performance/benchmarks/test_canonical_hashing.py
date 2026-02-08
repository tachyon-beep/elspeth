"""Canonical JSON hashing benchmarks.

Measures throughput of RFC 8785 canonicalization and SHA-256 hashing
for various row sizes. Critical for validating that audit hashing
doesn't become a bottleneck in high-throughput pipelines.
"""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.core.canonical import stable_hash
from tests.performance.conftest import benchmark_timer


def _small_row() -> dict[str, Any]:
    """Small flat row (~100 bytes serialized)."""
    return {
        "id": 12345,
        "name": "test_record",
        "value": 42.5,
        "active": True,
    }


def _medium_row() -> dict[str, Any]:
    """Medium nested row (~5KB serialized)."""
    return {
        "id": 12345,
        "metadata": {
            "source": "api",
            "timestamp": "2026-01-29T12:00:00Z",
            "tags": ["important", "validated", "processed"],
        },
        "payload": {
            "items": [{"sku": f"SKU-{i}", "quantity": i * 10, "price": i * 1.5} for i in range(100)],
        },
        "nested": {
            "level1": {
                "level2": {
                    "level3": {"deep_value": "found"},
                },
            },
        },
    }


def _large_row() -> dict[str, Any]:
    """Large LLM-response-like row (~50KB serialized)."""
    return {
        "id": 12345,
        "llm_response": {
            "content": "x" * 40000,
            "model": "gpt-4",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 2000},
        },
        "extracted_entities": [
            {
                "type": "PERSON",
                "value": f"Person {i}",
                "confidence": 0.95,
                "span": {"start": i * 10, "end": i * 10 + 8},
            }
            for i in range(200)
        ],
        "classification": {
            "category": "technical",
            "subcategories": ["engineering", "software", "data"],
            "scores": {f"label_{i}": 0.1 * (i % 10) for i in range(50)},
        },
    }


@pytest.mark.performance
def test_hash_throughput_small_rows() -> None:
    """Hash 1000 small flat dicts, measure rows/sec.

    Small rows are the most common case in tabular pipelines.
    Hashing should not be a bottleneck.
    """
    row = _small_row()
    iterations = 1000

    with benchmark_timer() as timing:
        for _ in range(iterations):
            stable_hash(row)

    rows_per_sec = iterations / timing.wall_seconds

    # Baseline: small rows should hash at > 5000 rows/sec
    assert rows_per_sec > 5000, f"Small row hashing: {rows_per_sec:.0f} rows/sec (expected > 5000)"


@pytest.mark.performance
def test_hash_throughput_medium_rows() -> None:
    """Hash 1000 medium nested dicts, measure rows/sec.

    Medium rows with nested structures exercise the recursive
    normalization path.
    """
    row = _medium_row()
    iterations = 1000

    with benchmark_timer() as timing:
        for _ in range(iterations):
            stable_hash(row)

    rows_per_sec = iterations / timing.wall_seconds

    # Baseline: medium rows should hash at > 500 rows/sec
    assert rows_per_sec > 500, f"Medium row hashing: {rows_per_sec:.0f} rows/sec (expected > 500)"


@pytest.mark.performance
def test_hash_throughput_large_rows() -> None:
    """Hash 100 large dicts (~50KB each), measure rows/sec.

    Large rows (LLM responses) test string-heavy canonicalization.
    """
    row = _large_row()
    iterations = 100

    with benchmark_timer() as timing:
        for _ in range(iterations):
            stable_hash(row)

    rows_per_sec = iterations / timing.wall_seconds

    # Baseline: large rows should hash at > 50 rows/sec
    assert rows_per_sec > 50, f"Large row hashing: {rows_per_sec:.0f} rows/sec (expected > 50)"


@pytest.mark.performance
def test_hash_consistency_across_iterations() -> None:
    """Same input produces same hash 1000 times (correctness + perf).

    Verifies determinism of RFC 8785 canonicalization while also
    serving as a throughput measurement.
    """
    row = _medium_row()
    iterations = 1000

    # First hash establishes the expected value
    expected_hash = stable_hash(row)

    with benchmark_timer() as timing:
        for _ in range(iterations):
            result = stable_hash(row)
            assert result == expected_hash

    rows_per_sec = iterations / timing.wall_seconds

    # The assertion loop adds overhead, but should still be > 200 rows/sec
    assert rows_per_sec > 200, f"Hash consistency check: {rows_per_sec:.0f} rows/sec (expected > 200)"
