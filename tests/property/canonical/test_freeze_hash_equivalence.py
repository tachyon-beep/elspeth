"""Property test: frozen and unfrozen data produce identical hashes.

This is the core invariant for freeze/serialize coherence:
canonical_json(deep_freeze(x)) == canonical_json(x) for all JSON-like x.

Uses contracts.hashing (not core.canonical) because that's the module
we fixed. Core.canonical already passed via the Mapping ABC.
"""

from __future__ import annotations

from hypothesis import given, settings

from elspeth.contracts.freeze import deep_freeze
from elspeth.contracts.hashing import canonical_json, stable_hash
from tests.strategies.json import json_values


@given(data=json_values)
@settings(max_examples=200)
def test_canonical_json_frozen_equals_unfrozen(data: object) -> None:
    """canonical_json(deep_freeze(x)) must equal canonical_json(x)."""
    frozen = deep_freeze(data)
    assert canonical_json(frozen) == canonical_json(data)


@given(data=json_values)
@settings(max_examples=200)
def test_stable_hash_frozen_equals_unfrozen(data: object) -> None:
    """stable_hash(deep_freeze(x)) must equal stable_hash(x)."""
    frozen = deep_freeze(data)
    assert stable_hash(frozen) == stable_hash(data)
