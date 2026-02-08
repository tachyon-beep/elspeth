"""Tests for web scrape content extraction utilities."""

import html2text
from hypothesis import given
from hypothesis.strategies import text

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


def test_html2text_deterministic_simple():
    """html2text must produce identical output for identical input."""
    html = "<html><body><h1>Title</h1><p>Content</p></body></html>"

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0

    result1 = h.handle(html)
    result2 = h.handle(html)

    assert result1 == result2, "html2text output is non-deterministic!"


@given(text(min_size=10, max_size=200))
def test_html2text_deterministic_property(content: str):
    """Property test: html2text must be deterministic for all inputs."""
    # Wrap content in minimal HTML structure
    html = f"<html><body><p>{content}</p></body></html>"

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0

    result1 = h.handle(html)
    result2 = h.handle(html)

    assert result1 == result2, f"Non-deterministic for input: {html!r}"


def test_html2text_deterministic_across_instances():
    """Verify determinism even with separate HTML2Text instances."""
    html = "<html><body><h1>Test</h1><p>Content</p></body></html>"

    h1 = html2text.HTML2Text()
    h1.ignore_links = False
    h1.body_width = 0

    h2 = html2text.HTML2Text()
    h2.ignore_links = False
    h2.body_width = 0

    result1 = h1.handle(html)
    result2 = h2.handle(html)

    assert result1 == result2, "html2text not deterministic across instances!"
