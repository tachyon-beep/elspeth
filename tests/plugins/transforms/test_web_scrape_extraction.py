"""Tests for web scrape content extraction utilities."""

from elspeth.plugins.transforms.web_scrape_extraction import extract_content


def test_extract_content_markdown():
    """HTML should convert to markdown."""
    html = "<html><body><h1>Title</h1><p>Content here</p></body></html>"

    result = extract_content(html, format="markdown")

    assert "# Title" in result
    assert "Content here" in result


def test_extract_content_text():
    """HTML should convert to plain text."""
    html = "<html><body><h1>Title</h1><p>Content</p></body></html>"

    result = extract_content(html, format="text")

    assert "Title" in result
    assert "Content" in result
    assert "<h1>" not in result  # No HTML tags


def test_extract_content_raw():
    """Raw format should return HTML unchanged."""
    html = "<html><body><h1>Test</h1></body></html>"

    result = extract_content(html, format="raw")

    assert result == html


def test_extract_content_strips_configured_elements():
    """Should remove configured HTML elements."""
    html = """
    <html>
        <head><script>alert('bad')</script></head>
        <body>
            <nav>Navigation</nav>
            <main><p>Content</p></main>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = extract_content(
        html,
        format="text",
        strip_elements=["script", "nav", "footer"],
    )

    assert "Content" in result
    assert "Navigation" not in result
    assert "Footer" not in result
    assert "alert" not in result
