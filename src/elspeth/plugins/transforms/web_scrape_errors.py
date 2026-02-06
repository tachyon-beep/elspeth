"""Error hierarchy for web scraping transform.

Follows LLM plugin pattern: retryable errors are re-raised for engine
RetryManager, non-retryable errors return TransformResult.error().
"""


class WebScrapeError(Exception):
    """Base error for web scrape transform."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


# Retryable errors (re-raise for engine retry)


class RateLimitError(WebScrapeError):
    """HTTP 429 or rate limit exceeded."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class NetworkError(WebScrapeError):
    """Network/connection errors (DNS, timeout, connection refused)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ServerError(WebScrapeError):
    """HTTP 5xx server errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class TimeoutError(WebScrapeError):
    """HTTP 408 Request Timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


# Non-retryable errors (return TransformResult.error())


class NotFoundError(WebScrapeError):
    """HTTP 404 Not Found."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ForbiddenError(WebScrapeError):
    """HTTP 403 Forbidden."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class UnauthorizedError(WebScrapeError):
    """HTTP 401 Unauthorized."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class SSLError(WebScrapeError):
    """SSL/TLS certificate validation failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class InvalidURLError(WebScrapeError):
    """Malformed or invalid URL."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ParseError(WebScrapeError):
    """HTML parsing or conversion failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class SSRFBlockedError(WebScrapeError):
    """URL resolves to blocked IP range (private, loopback, cloud metadata)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ResponseTooLargeError(WebScrapeError):
    """Response exceeds max_response_size_mb limit."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ConversionTimeoutError(WebScrapeError):
    """HTML-to-text/markdown conversion exceeded timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)
