# tests/core/landscape/test_secret_resolutions.py
"""Tests for secret resolution audit trail recording.

P2-10: Key Vault secrets configuration feature - Task 7.

Tests verify that secret resolutions are recorded correctly in the audit
trail with fingerprints (not actual secret values).
"""

from __future__ import annotations

import time

from sqlalchemy import select

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.landscape.schema import secret_resolutions_table
from elspeth.core.security.fingerprint import secret_fingerprint


class TestRecordSecretResolutions:
    """Tests for LandscapeRecorder.record_secret_resolutions()."""

    def test_records_single_resolution(self) -> None:
        """Single secret resolution is recorded with correct fields."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Create a run first (FK constraint)
        run = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )

        # Resolution record with pre-computed fingerprint (as load_secrets_from_config now returns)
        fingerprint_key = b"test-fingerprint-key"
        secret_value = "super-secret-api-key-12345"
        expected_fingerprint = secret_fingerprint(secret_value, key=fingerprint_key)
        timestamp = time.time()

        resolutions = [
            {
                "env_var_name": "AZURE_OPENAI_KEY",
                "source": "keyvault",
                "vault_url": "https://myvault.vault.azure.net",
                "secret_name": "azure-openai-key",
                "timestamp": timestamp,
                "latency_ms": 150.5,
                "fingerprint": expected_fingerprint,
            }
        ]

        # Record the resolutions
        recorder.record_secret_resolutions(
            run_id=run.run_id,
            resolutions=resolutions,
        )

        # Verify stored in database
        with db.connection() as conn:
            result = conn.execute(select(secret_resolutions_table).where(secret_resolutions_table.c.run_id == run.run_id))
            rows = result.fetchall()

        assert len(rows) == 1
        row = rows[0]

        # Verify fields
        assert row.run_id == run.run_id
        assert row.env_var_name == "AZURE_OPENAI_KEY"
        assert row.source == "keyvault"
        assert row.vault_url == "https://myvault.vault.azure.net"
        assert row.secret_name == "azure-openai-key"
        assert row.timestamp == timestamp
        assert row.resolution_latency_ms == 150.5

        # Verify fingerprint is stored correctly (NOT the raw secret)
        assert row.fingerprint == expected_fingerprint
        assert row.fingerprint != secret_value  # Sanity check: not the raw secret

    def test_records_multiple_resolutions(self) -> None:
        """Multiple secret resolutions are recorded in one call."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )

        fingerprint_key = b"test-fingerprint-key"
        timestamp = time.time()

        # Pre-compute fingerprints (as load_secrets_from_config now does)
        secrets = {
            "API_KEY_1": "secret-value-1",
            "API_KEY_2": "secret-value-2",
            "DB_PASSWORD": "secret-db-password",
        }

        resolutions = [
            {
                "env_var_name": "API_KEY_1",
                "source": "keyvault",
                "vault_url": "https://vault1.vault.azure.net",
                "secret_name": "api-key-1",
                "timestamp": timestamp,
                "latency_ms": 100.0,
                "fingerprint": secret_fingerprint(secrets["API_KEY_1"], key=fingerprint_key),
            },
            {
                "env_var_name": "API_KEY_2",
                "source": "keyvault",
                "vault_url": "https://vault1.vault.azure.net",
                "secret_name": "api-key-2",
                "timestamp": timestamp + 0.1,
                "latency_ms": 120.0,
                "fingerprint": secret_fingerprint(secrets["API_KEY_2"], key=fingerprint_key),
            },
            {
                "env_var_name": "DB_PASSWORD",
                "source": "keyvault",
                "vault_url": "https://vault2.vault.azure.net",
                "secret_name": "database-password",
                "timestamp": timestamp + 0.2,
                "latency_ms": 200.0,
                "fingerprint": secret_fingerprint(secrets["DB_PASSWORD"], key=fingerprint_key),
            },
        ]

        recorder.record_secret_resolutions(
            run_id=run.run_id,
            resolutions=resolutions,
        )

        # Verify no plaintext values in resolution records
        for r in resolutions:
            assert "secret_value" not in r

        # Verify all stored
        with db.connection() as conn:
            result = conn.execute(
                select(secret_resolutions_table)
                .where(secret_resolutions_table.c.run_id == run.run_id)
                .order_by(secret_resolutions_table.c.timestamp)
            )
            rows = result.fetchall()

        assert len(rows) == 3

        # Verify each has unique resolution_id
        resolution_ids = {row.resolution_id for row in rows}
        assert len(resolution_ids) == 3

        # Verify each has correct fingerprint
        for row in rows:
            expected_fp = secret_fingerprint(secrets[row.env_var_name], key=fingerprint_key)
            assert row.fingerprint == expected_fp

    def test_empty_resolutions_does_nothing(self) -> None:
        """Empty resolutions list is a no-op."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )

        # Record empty list
        recorder.record_secret_resolutions(
            run_id=run.run_id,
            resolutions=[],
        )

        # Verify nothing stored
        with db.connection() as conn:
            result = conn.execute(select(secret_resolutions_table).where(secret_resolutions_table.c.run_id == run.run_id))
            rows = result.fetchall()

        assert len(rows) == 0

    def test_nullable_fields_handled(self) -> None:
        """Nullable fields (vault_url, secret_name, latency_ms) can be None."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )

        # Resolution with None for optional fields
        resolutions = [
            {
                "env_var_name": "SOME_VAR",
                "source": "keyvault",
                "vault_url": None,
                "secret_name": None,
                "timestamp": time.time(),
                "latency_ms": None,
                "fingerprint": secret_fingerprint("value", key=b"key"),
            }
        ]

        recorder.record_secret_resolutions(
            run_id=run.run_id,
            resolutions=resolutions,
        )

        with db.connection() as conn:
            result = conn.execute(select(secret_resolutions_table).where(secret_resolutions_table.c.run_id == run.run_id))
            row = result.fetchone()

        assert row is not None
        assert row.vault_url is None
        assert row.secret_name is None
        assert row.resolution_latency_ms is None

    def test_fingerprint_differs_for_different_secrets(self) -> None:
        """Different secret values produce different fingerprints."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )

        fingerprint_key = b"same-key-for-both"
        timestamp = time.time()

        resolutions = [
            {
                "env_var_name": "VAR_A",
                "source": "keyvault",
                "vault_url": "https://vault.vault.azure.net",
                "secret_name": "secret-a",
                "timestamp": timestamp,
                "latency_ms": 100.0,
                "fingerprint": secret_fingerprint("secret-value-AAA", key=fingerprint_key),
            },
            {
                "env_var_name": "VAR_B",
                "source": "keyvault",
                "vault_url": "https://vault.vault.azure.net",
                "secret_name": "secret-b",
                "timestamp": timestamp,
                "latency_ms": 100.0,
                "fingerprint": secret_fingerprint("secret-value-BBB", key=fingerprint_key),
            },
        ]

        recorder.record_secret_resolutions(
            run_id=run.run_id,
            resolutions=resolutions,
        )

        with db.connection() as conn:
            result = conn.execute(select(secret_resolutions_table).where(secret_resolutions_table.c.run_id == run.run_id))
            rows = result.fetchall()

        fingerprints = {row.fingerprint for row in rows}
        assert len(fingerprints) == 2  # Different secrets = different fingerprints

    def test_same_secret_same_key_produces_same_fingerprint(self) -> None:
        """Same secret value with same key produces identical fingerprint."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        fingerprint_key = b"consistent-key"
        secret_value = "the-same-secret"
        fp = secret_fingerprint(secret_value, key=fingerprint_key)

        # First run
        run1 = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )
        recorder.record_secret_resolutions(
            run_id=run1.run_id,
            resolutions=[
                {
                    "env_var_name": "MY_SECRET",
                    "source": "keyvault",
                    "vault_url": "https://vault.vault.azure.net",
                    "secret_name": "my-secret",
                    "timestamp": time.time(),
                    "latency_ms": 100.0,
                    "fingerprint": fp,
                }
            ],
        )

        # Second run with same secret
        run2 = recorder.begin_run(
            config={"source": "test.csv"},
            canonical_version="v1",
        )
        recorder.record_secret_resolutions(
            run_id=run2.run_id,
            resolutions=[
                {
                    "env_var_name": "MY_SECRET",
                    "source": "keyvault",
                    "vault_url": "https://vault.vault.azure.net",
                    "secret_name": "my-secret",
                    "timestamp": time.time(),
                    "latency_ms": 100.0,
                    "fingerprint": fp,
                }
            ],
        )

        # Get fingerprints from both runs
        with db.connection() as conn:
            result = conn.execute(select(secret_resolutions_table))
            rows = result.fetchall()

        fingerprints = [row.fingerprint for row in rows]
        assert len(fingerprints) == 2
        assert fingerprints[0] == fingerprints[1]  # Same secret = same fingerprint
