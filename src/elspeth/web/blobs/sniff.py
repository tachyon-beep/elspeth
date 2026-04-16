"""Lightweight MIME content detection for uploaded blobs.

Inspects the first bytes of content to detect the actual data format.
Uses only stdlib (csv module for quote-aware field counting) — no
third-party dependencies. Detects the data-oriented types ELSPETH
accepts: CSV, JSON, JSONL, plain text.
"""

from __future__ import annotations

import csv
import io

# Minimum field (column) count to classify content as CSV. At 2 fields
# (1 delimiter per line), natural-language prose with a single comma
# ("Hello, world!\nGoodbye, world!") is indistinguishable from a
# 2-column CSV. Requiring 3+ fields eliminates this class of false
# positives. 2-column CSVs rely on the browser-declared MIME type.
_MIN_CSV_FIELDS = 3


def detect_mime_type(content: bytes) -> str | None:
    """Detect MIME type from content bytes. Returns None if uncertain.

    Only detects data-oriented formats relevant to ELSPETH:
    - JSON (starts with ``[`` or ``{`` after whitespace)
    - JSONL (multiple lines starting with ``{``)
    - CSV (2+ lines with consistent field counts >= 3, RFC 4180-aware)
    - Plain text (valid UTF-8 with no binary bytes)

    Returns None when content is ambiguous (e.g. delimiter-containing
    text with fewer than 3 columns) so the caller can fall back to the
    browser-declared MIME type.
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

    # CSV heuristic: require 2+ non-empty lines with consistent field
    # counts and at least 3 fields per row.  Uses csv.reader so that
    # quoted fields containing commas (RFC 4180) don't inflate the count.
    lines = stripped.split("\n", 10)
    non_empty = [line for line in lines if line.strip()]
    first_line = non_empty[0] if non_empty else ""
    has_delimiters = "," in first_line or "\t" in first_line

    if len(non_empty) >= 2 and has_delimiters:
        csv_sample = "\n".join(non_empty)
        for delimiter in (",", "\t"):
            try:
                reader = csv.reader(io.StringIO(csv_sample), delimiter=delimiter)
                field_counts = [len(row) for row in reader]
            except csv.Error:
                continue
            if field_counts and field_counts[0] >= _MIN_CSV_FIELDS and all(c == field_counts[0] for c in field_counts):
                return "text/csv"

    # Content has delimiters but didn't meet the CSV threshold (single-line,
    # <3 columns, or inconsistent counts).  Return None so the caller can
    # fall back to the browser-declared MIME type — a legitimate 2-column
    # CSV declared as text/csv should not be overridden.
    if has_delimiters:
        return None

    # No delimiters — definitively plain text.
    return "text/plain"
