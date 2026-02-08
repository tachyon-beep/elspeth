# tests_v2/property/testing/chaosllm/test_response_generator_properties.py
"""Property-based tests for ChaosLLM ResponseGenerator and PresetBank.

Tests the invariants of response generation:
- Determinism with seeded RNG
- OpenAIResponse structure correctness (to_dict() schema)
- Token estimation is always >= 1
- Random text word count within [min_words, max_words]
- Echo mode truncation at 200 characters
- PresetBank sequential cycling wraps around modulo N
- PresetBank random selection stays within bounds
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.testing.chaosllm.config import (
    RandomResponseConfig,
    ResponseConfig,
    TemplateResponseConfig,
)
from elspeth.testing.chaosllm.response_generator import (
    ENGLISH_VOCABULARY,
    LOREM_VOCABULARY,
    OpenAIResponse,
    PresetBank,
    ResponseGenerator,
)


# =============================================================================
# OpenAIResponse Structure
# =============================================================================


class TestOpenAIResponseStructure:
    """Property tests for OpenAIResponse.to_dict() schema compliance."""

    @given(
        content=st.text(min_size=0, max_size=200),
        model=st.sampled_from(["gpt-4", "gpt-3.5-turbo", "custom-model"]),
        prompt_tokens=st.integers(min_value=1, max_value=10000),
        completion_tokens=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=100)
    def test_to_dict_has_required_fields(
        self, content: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        """Property: to_dict() produces OpenAI-compatible response structure."""
        resp = OpenAIResponse(
            id="fake-abc123",
            object="chat.completion",
            created=1700000000,
            model=model,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason="stop",
        )

        d = resp.to_dict()

        # Top-level fields
        assert d["id"] == "fake-abc123"
        assert d["object"] == "chat.completion"
        assert d["model"] == model
        assert d["created"] == 1700000000

        # Choices structure
        assert len(d["choices"]) == 1
        choice = d["choices"][0]
        assert choice["index"] == 0
        assert choice["message"]["role"] == "assistant"
        assert choice["message"]["content"] == content
        assert choice["finish_reason"] == "stop"

        # Usage structure
        assert d["usage"]["prompt_tokens"] == prompt_tokens
        assert d["usage"]["completion_tokens"] == completion_tokens
        assert d["usage"]["total_tokens"] == prompt_tokens + completion_tokens

    @given(
        prompt_tokens=st.integers(min_value=0, max_value=100000),
        completion_tokens=st.integers(min_value=0, max_value=100000),
    )
    @settings(max_examples=100)
    def test_total_tokens_is_sum(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Property: total_tokens == prompt_tokens + completion_tokens."""
        resp = OpenAIResponse(
            id="fake-x",
            object="chat.completion",
            created=0,
            model="m",
            content="",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason="stop",
        )
        assert resp.total_tokens == prompt_tokens + completion_tokens


# =============================================================================
# Token Estimation
# =============================================================================


class TestTokenEstimation:
    """Property tests for token estimation."""

    @given(text=st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_token_estimate_always_positive(self, text: str) -> None:
        """Property: Token estimation is always >= 1."""
        config = ResponseConfig()
        gen = ResponseGenerator(config)
        tokens = gen._estimate_tokens(text)
        assert tokens >= 1, f"Token estimate {tokens} for text of length {len(text)}"


# =============================================================================
# Random Mode Properties
# =============================================================================


class TestRandomMode:
    """Property tests for random text generation."""

    @given(
        min_words=st.integers(min_value=1, max_value=20),
        max_words=st.integers(min_value=20, max_value=100),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
        vocabulary=st.sampled_from(["english", "lorem"]),
    )
    @settings(max_examples=100)
    def test_random_word_count_within_bounds(
        self, min_words: int, max_words: int, seed: int, vocabulary: str
    ) -> None:
        """Property: Random text word count is in [min_words, max_words]."""
        config = ResponseConfig(
            mode="random",
            random=RandomResponseConfig(
                min_words=min_words,
                max_words=max_words,
                vocabulary=vocabulary,
            ),
        )
        rng = random.Random(seed)
        gen = ResponseGenerator(config, rng=rng)

        text = gen._generate_random_text()
        # Text ends with a period, so strip it before counting words
        word_count = len(text.rstrip(".").split())
        assert min_words <= word_count <= max_words, (
            f"Word count {word_count} outside [{min_words}, {max_words}]"
        )

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_random_text_ends_with_period(self, seed: int) -> None:
        """Property: Random text always ends with a period."""
        config = ResponseConfig(mode="random")
        rng = random.Random(seed)
        gen = ResponseGenerator(config, rng=rng)

        text = gen._generate_random_text()
        assert text.endswith("."), f"Random text does not end with period: {text!r}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_random_text_first_word_capitalized(self, seed: int) -> None:
        """Property: Random text first word is capitalized."""
        config = ResponseConfig(mode="random")
        rng = random.Random(seed)
        gen = ResponseGenerator(config, rng=rng)

        text = gen._generate_random_text()
        assert text[0].isupper(), f"First character not uppercase: {text!r}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_english_vocabulary_used(self, seed: int) -> None:
        """Property: English vocabulary words come from ENGLISH_VOCABULARY."""
        config = ResponseConfig(
            mode="random",
            random=RandomResponseConfig(vocabulary="english"),
        )
        rng = random.Random(seed)
        gen = ResponseGenerator(config, rng=rng)

        text = gen._generate_random_text()
        words = text.rstrip(".").lower().split()
        for word in words:
            assert word in ENGLISH_VOCABULARY, f"Word {word!r} not in ENGLISH_VOCABULARY"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_lorem_vocabulary_used(self, seed: int) -> None:
        """Property: Lorem vocabulary words come from LOREM_VOCABULARY."""
        config = ResponseConfig(
            mode="random",
            random=RandomResponseConfig(vocabulary="lorem"),
        )
        rng = random.Random(seed)
        gen = ResponseGenerator(config, rng=rng)

        text = gen._generate_random_text()
        words = text.rstrip(".").lower().split()
        for word in words:
            assert word in LOREM_VOCABULARY, f"Word {word!r} not in LOREM_VOCABULARY"


# =============================================================================
# Echo Mode Properties
# =============================================================================


class TestEchoMode:
    """Property tests for echo response generation."""

    @given(
        content=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=100)
    def test_echo_truncates_at_200_chars(self, content: str) -> None:
        """Property: Echo mode truncates at 200 characters."""
        config = ResponseConfig(mode="echo")
        gen = ResponseGenerator(config)

        request = {"messages": [{"role": "user", "content": content}]}
        echo = gen._generate_echo_response(request)

        # Echo adds "Echo: " prefix
        if len(content) > 200:
            assert echo.endswith("..."), f"Long content not truncated: {echo!r}"
            # "Echo: " (6) + content[:200] + "..." = 209 max
            assert len(echo) <= 209
        else:
            assert echo == f"Echo: {content}"

    def test_echo_empty_messages_fallback(self) -> None:
        """Edge case: No messages returns fallback."""
        config = ResponseConfig(mode="echo")
        gen = ResponseGenerator(config)

        result = gen._generate_echo_response({"messages": []})
        assert result == "Echo: (no messages provided)"


# =============================================================================
# Determinism with Seeded RNG
# =============================================================================


class TestDeterminism:
    """Property tests for deterministic behavior with seeded RNG."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_same_seed_same_response(self, seed: int) -> None:
        """Property: Same seed produces identical responses."""
        config = ResponseConfig(mode="random")
        request = {"messages": [{"role": "user", "content": "test"}], "model": "gpt-4"}

        rng1 = random.Random(seed)
        gen1 = ResponseGenerator(
            config, rng=rng1, time_func=lambda: 1700000000.0, uuid_func=lambda: "abc"
        )

        rng2 = random.Random(seed)
        gen2 = ResponseGenerator(
            config, rng=rng2, time_func=lambda: 1700000000.0, uuid_func=lambda: "abc"
        )

        for i in range(20):
            r1 = gen1.generate(request)
            r2 = gen2.generate(request)
            assert r1.content == r2.content, f"Diverged at iteration {i}"
            assert r1.prompt_tokens == r2.prompt_tokens
            assert r1.completion_tokens == r2.completion_tokens


# =============================================================================
# Generate() Integration Properties
# =============================================================================


class TestGenerateIntegration:
    """Property tests for the generate() method."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_generate_returns_valid_response(self, seed: int) -> None:
        """Property: generate() returns a well-formed OpenAIResponse."""
        config = ResponseConfig(mode="random")
        rng = random.Random(seed)
        gen = ResponseGenerator(
            config, rng=rng, time_func=lambda: 1700000000.0, uuid_func=lambda: "x"
        )

        request = {"messages": [{"role": "user", "content": "hello"}], "model": "gpt-4"}
        resp = gen.generate(request)

        assert resp.id.startswith("fake-")
        assert resp.object == "chat.completion"
        assert resp.created == 1700000000
        assert resp.model == "gpt-4"
        assert resp.finish_reason == "stop"
        assert resp.prompt_tokens >= 1
        assert resp.completion_tokens >= 1
        assert len(resp.content) > 0

    @given(
        mode=st.sampled_from(["random", "echo"]),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=50)
    def test_mode_override_respected(self, mode: str, seed: int) -> None:
        """Property: mode_override overrides config mode."""
        config = ResponseConfig(mode="random")
        rng = random.Random(seed)
        gen = ResponseGenerator(
            config, rng=rng, time_func=lambda: 0.0, uuid_func=lambda: "x"
        )

        request = {"messages": [{"role": "user", "content": "test"}], "model": "m"}
        resp = gen.generate(request, mode_override=mode)

        if mode == "echo":
            assert resp.content.startswith("Echo: ")
        # Random mode just produces some text (no prefix to check)


# =============================================================================
# PresetBank Properties
# =============================================================================


class TestPresetBank:
    """Property tests for PresetBank cycling behavior."""

    @given(
        n_responses=st.integers(min_value=1, max_value=20),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=50)
    def test_sequential_cycling_wraps(self, n_responses: int, seed: int) -> None:
        """Property: Sequential mode cycles through responses modulo N."""
        responses = [f"response_{i}" for i in range(n_responses)]
        bank = PresetBank(responses, selection="sequential")

        # Cycle through 3x the length
        for cycle in range(3):
            for i in range(n_responses):
                result = bank.next()
                assert result == f"response_{i}", (
                    f"Cycle {cycle}, index {i}: expected response_{i}, got {result}"
                )

    @given(
        n_responses=st.integers(min_value=1, max_value=20),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=50)
    def test_random_selection_within_bounds(self, n_responses: int, seed: int) -> None:
        """Property: Random mode only returns items from the responses list."""
        responses = [f"response_{i}" for i in range(n_responses)]
        rng = random.Random(seed)
        bank = PresetBank(responses, selection="random", rng=rng)

        for _ in range(100):
            result = bank.next()
            assert result in responses, f"Got {result!r} not in responses"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_reset_restarts_sequential(self, seed: int) -> None:
        """Property: reset() restarts sequential cycling from index 0."""
        responses = ["a", "b", "c"]
        bank = PresetBank(responses, selection="sequential")

        # Advance a few steps
        bank.next()  # "a"
        bank.next()  # "b"
        bank.reset()

        assert bank.next() == "a", "After reset, should start from index 0"

    def test_empty_responses_raises(self) -> None:
        """Edge case: Empty responses list raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="at least one response"):
            PresetBank([], selection="sequential")
