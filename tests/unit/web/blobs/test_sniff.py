"""Tests for detect_mime_type — content-based MIME sniffing.

Verifies the byte-prefix heuristics for data-oriented formats:
- JSON (object and array)
- JSONL (multiple { lines)
- CSV (comma and tab delimited)
- Plain text (valid UTF-8, no markers)
- Binary (null bytes or invalid UTF-8)
- Edge cases (empty, BOM, whitespace)
"""

from __future__ import annotations

from elspeth.web.blobs.sniff import detect_mime_type


class TestJsonDetection:
    """JSON starts with [ or { after optional whitespace."""

    def test_json_array(self) -> None:
        assert detect_mime_type(b'[{"id": 1}]') == "application/json"

    def test_json_object(self) -> None:
        assert detect_mime_type(b'{"key": "value"}') == "application/json"

    def test_json_with_leading_whitespace(self) -> None:
        assert detect_mime_type(b'  \n  {"key": "value"}') == "application/json"

    def test_json_array_with_bom(self) -> None:
        assert detect_mime_type(b"\xef\xbb\xbf" + b"[1, 2, 3]") == "application/json"


class TestJsonlDetection:
    """JSONL: multiple lines starting with {."""

    def test_jsonl_two_lines(self) -> None:
        content = b'{"a": 1}\n{"b": 2}\n'
        assert detect_mime_type(content) == "application/x-jsonlines"

    def test_jsonl_three_lines(self) -> None:
        content = b'{"a": 1}\n{"b": 2}\n{"c": 3}\n'
        assert detect_mime_type(content) == "application/x-jsonlines"

    def test_single_json_object_not_jsonl(self) -> None:
        """One { line is JSON, not JSONL."""
        assert detect_mime_type(b'{"only": "one"}') == "application/json"


class TestCsvDetection:
    """CSV: comma or tab in first line, no JSON markers."""

    def test_comma_delimited(self) -> None:
        assert detect_mime_type(b"name,age,city\nAlice,30,London") == "text/csv"

    def test_tab_delimited(self) -> None:
        assert detect_mime_type(b"name\tage\tcity\nAlice\t30\tLondon") == "text/csv"

    def test_csv_with_bom(self) -> None:
        assert detect_mime_type(b"\xef\xbb\xbf" + b"a,b,c\n1,2,3") == "text/csv"


class TestPlainText:
    """Plain text: valid UTF-8 without JSON or CSV markers."""

    def test_plain_text(self) -> None:
        assert detect_mime_type(b"Hello, world!") == "text/csv"  # has comma → CSV

    def test_no_delimiters(self) -> None:
        assert detect_mime_type(b"Just some plain text") == "text/plain"

    def test_whitespace_only(self) -> None:
        assert detect_mime_type(b"   \n  \n  ") == "text/plain"


class TestBinaryDetection:
    """Binary: null bytes or invalid UTF-8."""

    def test_null_bytes(self) -> None:
        assert detect_mime_type(b"\x00\x01\x02\x03") == "application/octet-stream"

    def test_invalid_utf8(self) -> None:
        assert detect_mime_type(b"\x80\x81\x82") == "application/octet-stream"

    def test_mixed_text_with_null(self) -> None:
        assert detect_mime_type(b"header\x00binary") == "application/octet-stream"


class TestEdgeCases:
    """Empty content and other edge cases."""

    def test_empty_bytes(self) -> None:
        assert detect_mime_type(b"") is None

    def test_bom_only(self) -> None:
        """BOM with no content after stripping."""
        assert detect_mime_type(b"\xef\xbb\xbf") == "text/plain"
