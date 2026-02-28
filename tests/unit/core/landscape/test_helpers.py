"""Tests for landscape helper functions."""

from datetime import UTC, datetime

from elspeth.core.landscape._helpers import generate_id, now


class TestNow:
    """Tests for now() helper."""

    def test_returns_utc_datetime(self) -> None:
        """now() returns UTC datetime."""
        result = now()
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_returns_current_time(self) -> None:
        """now() returns approximately current time."""
        before = datetime.now(UTC)
        result = now()
        after = datetime.now(UTC)
        assert before <= result <= after


class TestGenerateId:
    """Tests for generate_id() helper."""

    def test_returns_hex_string(self) -> None:
        """generate_id() returns hex string."""
        result = generate_id()
        assert isinstance(result, str)
        # UUID4 hex is 32 characters
        assert len(result) == 32
        # All characters are hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_returns_unique_ids(self) -> None:
        """generate_id() returns unique IDs each call."""
        ids = [generate_id() for _ in range(100)]
        assert len(set(ids)) == 100
