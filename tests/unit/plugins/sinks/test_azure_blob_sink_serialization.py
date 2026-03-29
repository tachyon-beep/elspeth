"""Tests for AzureBlobSink JSON serialization boundary.

Verifies that non-finite floats are rejected at serialization time
rather than producing non-standard JSON blobs.
"""

import pytest


class TestAzureBlobSinkNonFiniteRejection:
    """Non-finite floats must be rejected at the JSON/JSONL serialization boundary."""

    @pytest.fixture
    def sink(self):
        """Create sink with minimal config, no Azure connection needed."""
        from elspeth.plugins.sinks.azure_blob_sink import AzureBlobSink

        return AzureBlobSink(
            {
                "container": "test-container",
                "blob_path": "test.json",
                "format": "json",
                "connection_string": "DefaultEndpointsProtocol=https;AccountName=fake;AccountKey=ZmFrZQ==;EndpointSuffix=core.windows.net",
                "schema": {"mode": "observed"},
            }
        )

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "neg_inf"])
    def test_serialize_json_rejects_non_finite(self, sink, bad_value: float) -> None:
        with pytest.raises(ValueError, match="Out of range float values"):
            sink._serialize_json([{"id": 1, "value": bad_value}])

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "neg_inf"])
    def test_serialize_jsonl_rejects_non_finite(self, sink, bad_value: float) -> None:
        with pytest.raises(ValueError, match="Out of range float values"):
            sink._serialize_jsonl([{"id": 1, "value": bad_value}])

    def test_serialize_json_accepts_finite_floats(self, sink) -> None:
        result = sink._serialize_json([{"id": 1, "value": 3.14}])
        assert b"3.14" in result

    def test_serialize_jsonl_accepts_finite_floats(self, sink) -> None:
        result = sink._serialize_jsonl([{"id": 1, "value": 3.14}])
        assert b"3.14" in result
