# tests/strategies/settings.py
"""Standardized Hypothesis settings profiles for property tests.

Tiers:
- DETERMINISM_SETTINGS: 500 examples - P0 hash/canonical tests
- STATE_MACHINE_SETTINGS: 200 examples - Stateful tests
- STANDARD_SETTINGS: 100 examples - Regular property tests
- SLOW_SETTINGS: 50 examples - I/O bound tests
- QUICK_SETTINGS: 20 examples - Fast validation tests
"""

from hypothesis import settings

DETERMINISM_SETTINGS = settings(max_examples=500)
STATE_MACHINE_SETTINGS = settings(max_examples=200)
STANDARD_SETTINGS = settings(max_examples=100)
SLOW_SETTINGS = settings(max_examples=50)
QUICK_SETTINGS = settings(max_examples=20)
