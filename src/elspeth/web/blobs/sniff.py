"""Lightweight MIME content detection for uploaded blobs.

Inspects the first bytes of content to detect the actual data format.
No external dependencies — just byte-prefix heuristics for the
data-oriented types ELSPETH accepts (CSV, JSON, JSONL, plain text).
"""

from __future__ import annotations


def detect_mime_type(content: bytes) -> str | None:
    """Detect MIME type from content bytes. Returns None if uncertain.

    Only detects data-oriented formats relevant to ELSPETH:
    - JSON (starts with [ or { after whitespace)
    - CSV (heuristic: first line contains commas/tabs with no JSON markers)
    - Plain text (valid UTF-8 with no binary bytes)

    Returns None rather than guessing when the content is ambiguous.
    """
    if not content:
        return None

    # Strip UTF-8 BOM if present
    sample = content[:4096]
    if sample.startswith(b"\xef\xbb\xbf"):
        sample = sample[3:]

    # Check for binary content (non-text bytes)
    # Null bytes are a strong indicator of binary content
    if b"\x00" in sample:
        return "application/octet-stream"

    # Try decoding as UTF-8
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"

    stripped = text.lstrip()
    if not stripped:
        return "text/plain"

    # JSON: starts with [ or {
    if stripped[0] == "[":
        return "application/json"
    if stripped[0] == "{":
        # Could be JSON object or JSONL — check if multiple lines start with {
        lines = stripped.split("\n", 3)
        json_lines = sum(1 for line in lines if line.strip().startswith("{"))
        if json_lines > 1:
            return "application/x-jsonlines"
        return "application/json"

    # CSV heuristic: first line contains comma or tab delimiters,
    # and doesn't look like JSON
    first_line = stripped.split("\n", 1)[0]
    if "," in first_line or "\t" in first_line:
        return "text/csv"

    return "text/plain"
