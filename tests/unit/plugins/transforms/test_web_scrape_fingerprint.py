from elspeth.plugins.transforms.web_scrape_fingerprint import compute_fingerprint


def test_fingerprint_deterministic():
    """Same content should produce same fingerprint."""
    content = "Hello world"

    fp1 = compute_fingerprint(content, mode="content")
    fp2 = compute_fingerprint(content, mode="content")

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_content_mode_whitespace_insensitive():
    """Content mode should ignore whitespace changes."""
    content1 = "Hello world"
    content2 = "Hello   world"
    content3 = "Hello\n\nworld"

    fp1 = compute_fingerprint(content1, mode="content")
    fp2 = compute_fingerprint(content2, mode="content")
    fp3 = compute_fingerprint(content3, mode="content")

    assert fp1 == fp2 == fp3


def test_fingerprint_full_mode_whitespace_sensitive():
    """Full mode should detect whitespace changes."""
    content1 = "Hello world"
    content2 = "Hello   world"

    fp1 = compute_fingerprint(content1, mode="full")
    fp2 = compute_fingerprint(content2, mode="full")

    assert fp1 != fp2


def test_fingerprint_content_mode_detects_text_changes():
    """Content mode should detect meaningful text changes."""
    content1 = "The policy is active"
    content2 = "The policy is inactive"

    fp1 = compute_fingerprint(content1, mode="content")
    fp2 = compute_fingerprint(content2, mode="content")

    assert fp1 != fp2
