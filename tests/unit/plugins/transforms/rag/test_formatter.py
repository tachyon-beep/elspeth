"""Tests for RAG context formatting."""

from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk
from elspeth.plugins.transforms.rag.formatter import format_context


def _chunk(content: str, score: float = 0.9) -> RetrievalChunk:
    return RetrievalChunk(content=content, score=score, source_id="doc1", metadata={})


class TestNumberedFormat:
    def test_multiple_chunks(self):
        chunks = [_chunk("First chunk"), _chunk("Second chunk")]
        result = format_context(chunks, format_mode="numbered")
        assert result.text == "1. First chunk\n2. Second chunk"
        assert result.truncated is False

    def test_single_chunk(self):
        result = format_context([_chunk("Only chunk")], format_mode="numbered")
        assert result.text == "1. Only chunk"

    def test_empty_chunks(self):
        result = format_context([], format_mode="numbered")
        assert result.text == ""
        assert result.truncated is False


class TestSeparatedFormat:
    def test_with_default_separator(self):
        chunks = [_chunk("First"), _chunk("Second")]
        result = format_context(chunks, format_mode="separated", separator="\n---\n")
        assert result.text == "First\n---\nSecond"

    def test_with_custom_separator(self):
        chunks = [_chunk("A"), _chunk("B")]
        result = format_context(chunks, format_mode="separated", separator=" | ")
        assert result.text == "A | B"


class TestRawFormat:
    def test_concatenates_content(self):
        chunks = [_chunk("Hello"), _chunk("World")]
        result = format_context(chunks, format_mode="raw")
        assert result.text == "HelloWorld"


class TestMaxContextLength:
    def test_truncation_at_chunk_boundary(self):
        chunks = [_chunk("Short"), _chunk("Also short"), _chunk("Third")]
        # "1. Short\n2. Also short" = 22 chars, "1. Short" = 8 chars
        result = format_context(chunks, format_mode="numbered", max_length=22)
        assert "Short" in result.text
        assert "Also short" in result.text
        assert "Third" not in result.text
        assert result.truncated is True

    def test_first_chunk_exceeds_limit(self):
        """Hard-truncated output must not exceed max_length (including indicator)."""
        chunks = [_chunk("A very long chunk that exceeds the limit")]
        result = format_context(chunks, format_mode="numbered", max_length=20)
        assert len(result.text) <= 20, f"Truncated text length {len(result.text)} exceeds max_length 20: {result.text!r}"
        assert result.text.endswith("[truncated]")
        # Content before indicator should be the start of the numbered chunk
        assert result.text.startswith("1. A very"), f"Expected content prefix, got {result.text!r}"
        assert result.truncated is True

    def test_truncation_respects_exact_budget_raw(self):
        """The [truncated] indicator must fit within max_length (raw mode)."""
        chunks = [_chunk("x" * 100)]
        for max_len in [15, 20, 50, 100]:
            result = format_context(chunks, format_mode="raw", max_length=max_len)
            assert len(result.text) <= max_len, f"max_length={max_len} but got {len(result.text)} chars: {result.text!r}"

    def test_truncation_respects_exact_budget_numbered(self):
        """The [truncated] indicator must fit within max_length (numbered mode).

        Numbered mode adds a '1. ' prefix (3 chars) which is part of the budget.
        """
        chunks = [_chunk("x" * 100)]
        for max_len in [15, 20, 50, 100]:
            result = format_context(chunks, format_mode="numbered", max_length=max_len)
            assert len(result.text) <= max_len, f"max_length={max_len} but got {len(result.text)} chars: {result.text!r}"

    def test_truncation_with_max_length_smaller_than_indicator(self):
        """When max_length is too small for '[truncated]', hard truncate without indicator."""
        chunks = [_chunk("ABCDEFGHIJKLMNOP")]
        for max_len in [1, 5, 10, 11]:
            result = format_context(chunks, format_mode="raw", max_length=max_len)
            assert len(result.text) <= max_len, f"max_length={max_len} but got {len(result.text)} chars: {result.text!r}"
            assert result.truncated is True

    def test_no_truncation_when_within_limit(self):
        chunks = [_chunk("Short")]
        result = format_context(chunks, format_mode="numbered", max_length=1000)
        assert result.text == "1. Short"
        assert result.truncated is False

    def test_none_max_length_means_no_limit(self):
        long_content = "x" * 10000
        chunks = [_chunk(long_content)]
        result = format_context(chunks, format_mode="numbered", max_length=None)
        assert len(result.text) > 10000
        assert result.truncated is False
