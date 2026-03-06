"""Tests for TokenUsage frozen dataclass."""

from elspeth.contracts.token_usage import TokenUsage


class TestTokenUsageFactories:
    """Tests for known(), unknown(), and from_dict() factories."""

    def test_known_factory(self) -> None:
        usage = TokenUsage.known(10, 20)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20

    def test_unknown_factory(self) -> None:
        usage = TokenUsage.unknown()
        assert usage.prompt_tokens is None
        assert usage.completion_tokens is None

    def test_partial_known_prompt_only(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=None)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens is None

    def test_partial_known_completion_only(self) -> None:
        usage = TokenUsage(prompt_tokens=None, completion_tokens=20)
        assert usage.prompt_tokens is None
        assert usage.completion_tokens == 20

    def test_default_is_unknown(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens is None
        assert usage.completion_tokens is None

    def test_known_rejects_negative_prompt_tokens(self) -> None:
        """Negative token counts are physically impossible."""
        import pytest

        with pytest.raises(ValueError, match="prompt_tokens must be non-negative"):
            TokenUsage.known(-1, 20)

    def test_known_rejects_negative_completion_tokens(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="completion_tokens must be non-negative"):
            TokenUsage.known(10, -5)

    def test_direct_construction_rejects_negative(self) -> None:
        """Direct construction also validates (not just factories)."""
        import pytest

        with pytest.raises(ValueError, match="prompt_tokens must be non-negative"):
            TokenUsage(prompt_tokens=-100, completion_tokens=None)

    def test_zero_tokens_accepted(self) -> None:
        """Zero is valid (cached responses may report 0 completion tokens)."""
        usage = TokenUsage.known(0, 0)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0


class TestTokenUsageProperties:
    """Tests for total_tokens and is_known derived properties."""

    def test_total_tokens_known(self) -> None:
        usage = TokenUsage.known(10, 20)
        assert usage.total_tokens == 30

    def test_total_tokens_unknown(self) -> None:
        usage = TokenUsage.unknown()
        assert usage.total_tokens is None

    def test_total_tokens_partial_prompt_only(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=None)
        assert usage.total_tokens is None

    def test_total_tokens_partial_completion_only(self) -> None:
        usage = TokenUsage(prompt_tokens=None, completion_tokens=20)
        assert usage.total_tokens is None

    def test_total_tokens_zero(self) -> None:
        usage = TokenUsage.known(0, 0)
        assert usage.total_tokens == 0

    def test_is_known_true(self) -> None:
        usage = TokenUsage.known(10, 20)
        assert usage.is_known is True

    def test_is_known_false_unknown(self) -> None:
        usage = TokenUsage.unknown()
        assert usage.is_known is False

    def test_is_known_false_partial(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=None)
        assert usage.is_known is False

    def test_is_known_true_with_zeros(self) -> None:
        usage = TokenUsage.known(0, 0)
        assert usage.is_known is True


class TestTokenUsageToDict:
    """Tests for to_dict() serialization."""

    def test_to_dict_full(self) -> None:
        usage = TokenUsage.known(10, 20)
        assert usage.to_dict() == {"prompt_tokens": 10, "completion_tokens": 20}

    def test_to_dict_empty(self) -> None:
        usage = TokenUsage.unknown()
        assert usage.to_dict() == {}

    def test_to_dict_partial_prompt_only(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=None)
        assert usage.to_dict() == {"prompt_tokens": 10}

    def test_to_dict_partial_completion_only(self) -> None:
        usage = TokenUsage(prompt_tokens=None, completion_tokens=20)
        assert usage.to_dict() == {"completion_tokens": 20}

    def test_to_dict_zero_values(self) -> None:
        """Zero is a valid known value, not unknown."""
        usage = TokenUsage.known(0, 0)
        assert usage.to_dict() == {"prompt_tokens": 0, "completion_tokens": 0}


class TestTokenUsageFromDict:
    """Tests for from_dict() Tier 3 boundary reconstruction."""

    def test_from_dict_full(self) -> None:
        usage = TokenUsage.from_dict({"prompt_tokens": 10, "completion_tokens": 20})
        assert usage == TokenUsage.known(10, 20)

    def test_from_dict_empty(self) -> None:
        usage = TokenUsage.from_dict({})
        assert usage == TokenUsage.unknown()

    def test_from_dict_none_input(self) -> None:
        usage = TokenUsage.from_dict(None)
        assert usage == TokenUsage.unknown()

    def test_from_dict_non_dict_input(self) -> None:
        usage = TokenUsage.from_dict("not a dict")
        assert usage == TokenUsage.unknown()

    def test_from_dict_non_int_prompt_tokens(self) -> None:
        """Non-int values should be coerced to None."""
        usage = TokenUsage.from_dict({"prompt_tokens": "10", "completion_tokens": 20})
        assert usage.prompt_tokens is None
        assert usage.completion_tokens == 20

    def test_from_dict_non_int_completion_tokens(self) -> None:
        usage = TokenUsage.from_dict({"prompt_tokens": 10, "completion_tokens": 3.5})
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens is None

    def test_from_dict_null_values(self) -> None:
        usage = TokenUsage.from_dict({"prompt_tokens": None, "completion_tokens": None})
        assert usage == TokenUsage.unknown()

    def test_from_dict_missing_keys(self) -> None:
        usage = TokenUsage.from_dict({"total_tokens": 30})
        assert usage == TokenUsage.unknown()

    def test_from_dict_extra_keys_ignored(self) -> None:
        usage = TokenUsage.from_dict({"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "extra": "ignored"})
        assert usage == TokenUsage.known(10, 20)

    def test_from_dict_bool_coerced_to_none(self) -> None:
        """bool is subclass of int in Python, but True/False are not valid token counts."""
        usage = TokenUsage.from_dict({"prompt_tokens": True, "completion_tokens": False})
        assert usage.prompt_tokens is None
        assert usage.completion_tokens is None

    def test_from_dict_bool_prompt_with_valid_completion(self) -> None:
        """Bool in one field shouldn't affect valid int in the other."""
        usage = TokenUsage.from_dict({"prompt_tokens": True, "completion_tokens": 20})
        assert usage.prompt_tokens is None
        assert usage.completion_tokens == 20


class TestTokenUsageImmutability:
    """Tests for frozen dataclass invariants."""

    def test_frozen(self) -> None:
        usage = TokenUsage.known(10, 20)
        try:
            usage.prompt_tokens = 99  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # Expected — frozen dataclass

    def test_equality(self) -> None:
        a = TokenUsage.known(10, 20)
        b = TokenUsage.known(10, 20)
        assert a == b

    def test_inequality(self) -> None:
        a = TokenUsage.known(10, 20)
        b = TokenUsage.known(10, 30)
        assert a != b

    def test_hashable(self) -> None:
        usage = TokenUsage.known(10, 20)
        # Frozen dataclass with slots=True is hashable
        s = {usage}
        assert len(s) == 1

    def test_hash_consistency(self) -> None:
        a = TokenUsage.known(10, 20)
        b = TokenUsage.known(10, 20)
        assert hash(a) == hash(b)


class TestTokenUsageRoundTrip:
    """Tests for to_dict() → from_dict() round-trip."""

    def test_round_trip_known(self) -> None:
        original = TokenUsage.known(10, 20)
        restored = TokenUsage.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_unknown(self) -> None:
        original = TokenUsage.unknown()
        restored = TokenUsage.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_partial(self) -> None:
        original = TokenUsage(prompt_tokens=10, completion_tokens=None)
        restored = TokenUsage.from_dict(original.to_dict())
        assert restored == original
