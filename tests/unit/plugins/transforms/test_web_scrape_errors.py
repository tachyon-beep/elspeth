from elspeth.plugins.transforms.web_scrape_errors import (
    ForbiddenError,
    InvalidURLError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    SSRFBlockedError,
    UnauthorizedError,
)


def test_rate_limit_error_is_retryable():
    """RateLimitError should be retryable."""
    error = RateLimitError("Rate limit exceeded")
    assert error.retryable is True


def test_network_error_is_retryable():
    """NetworkError should be retryable."""
    error = NetworkError("Connection timeout")
    assert error.retryable is True


def test_server_error_is_retryable():
    """ServerError should be retryable."""
    error = ServerError("503 Service Unavailable")
    assert error.retryable is True


def test_not_found_error_is_not_retryable():
    """NotFoundError should not be retryable."""
    error = NotFoundError("404 Not Found")
    assert error.retryable is False


def test_forbidden_error_is_not_retryable():
    """ForbiddenError should not be retryable."""
    error = ForbiddenError("403 Forbidden")
    assert error.retryable is False


def test_unauthorized_error_is_not_retryable():
    """UnauthorizedError should not be retryable."""
    error = UnauthorizedError("401 Unauthorized")
    assert error.retryable is False


def test_invalid_url_error_is_not_retryable():
    """InvalidURLError should not be retryable."""
    error = InvalidURLError("Malformed URL")
    assert error.retryable is False


def test_ssrf_blocked_error_is_not_retryable():
    """SSRFBlockedError should not be retryable."""
    error = SSRFBlockedError("Blocked IP: 127.0.0.1")
    assert error.retryable is False
