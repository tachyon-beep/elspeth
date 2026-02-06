"""Content extraction utilities for web scraping.

Converts HTML to markdown, text, or raw format with configurable
element stripping.
"""

import html2text
from bs4 import BeautifulSoup


def extract_content(
    html: str,
    format: str,
    strip_elements: list[str] | None = None,
) -> str:
    """Extract content from HTML in specified format.

    Args:
        html: Raw HTML content
        format: Output format ("markdown", "text", "raw")
        strip_elements: HTML tags to remove before extraction

    Returns:
        Extracted content as string

    Raises:
        ValueError: If format is not one of "markdown", "text", "raw"
    """
    if format == "raw":
        return html

    # Parse HTML and strip unwanted elements
    soup = BeautifulSoup(html, "html.parser")

    if strip_elements:
        for tag_name in strip_elements:
            for tag in soup.find_all(tag_name):
                tag.decompose()

    # Extract based on format
    if format == "markdown":
        # Get cleaned HTML back from soup
        cleaned_html = str(soup)

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.body_width = 0  # Don't wrap lines
        h.ignore_tables = False
        h.ignore_emphasis = False

        return h.handle(cleaned_html)

    elif format == "text":
        return soup.get_text(separator=" ", strip=True)

    else:
        raise ValueError(f"Unknown format: {format}")
