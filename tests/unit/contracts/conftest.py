# tests/unit/contracts/conftest.py
"""Contract test configuration.

Provides payload_store fixture (MockPayloadStore) needed by
orchestrator wiring tests in test_telemetry_contracts.py.
"""

from tests.fixtures.stores import payload_store  # noqa: F401
