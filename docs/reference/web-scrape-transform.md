# Web Scrape Transform

Fetch webpages from URLs, convert content to markdown/text, and generate fingerprints for change detection.

## Configuration

```yaml
transforms:
  - plugin: web_scrape
    options:
      url_field: url
      content_field: page_content
      fingerprint_field: page_fingerprint
      format: markdown  # markdown | text | raw
      text_separator: " "  # text format only; use "\n" before line_explode
      fingerprint_mode: content  # content | full

      http:
        abuse_contact: compliance@example.com
        scraping_reason: "Compliance monitoring"
        timeout: 30

      strip_elements:
        - script
        - style
        - nav
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `{content_field}` | str | Extracted content |
| `{fingerprint_field}` | str | SHA-256 fingerprint |
| `fetch_status` | int | HTTP status code |
| `fetch_url_final` | str | Final URL after redirects |

## Text Extraction And Line Splitting

`format: text` defaults to `text_separator: " "`, which returns compact plain
text. If a downstream `line_explode` transform should emit one row per DOM text
segment, set `text_separator: "\n"` so the scraped content still contains line
breaks when it reaches the splitter.

## Security

- SSRF prevention (blocks private IPs, loopback, cloud metadata)
- Scheme whitelist (http/https only)
- SSL certificate verification (always enabled)

## Installation

```bash
uv pip install -e ".[web]"
```
