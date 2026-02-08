from elspeth.plugins.transforms.web_scrape_errors import (
    ConversionTimeoutError,
    ForbiddenError,
    InvalidURLError,
    NetworkError,
    NotFoundError,
    ParseError,
    RateLimitError,
    ResponseTooLargeError,
    ServerError,
    SSLError,
    SSRFBlockedError,
    TimeoutError,
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


def test_timeout_error_is_retryable():
    """TimeoutError should be retryable."""
    error = TimeoutError("408 Request Timeout")
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


def test_ssl_error_is_not_retryable():
    """SSLError should not be retryable."""
    error = SSLError("Certificate verification failed")
    assert error.retryable is False


def test_invalid_url_error_is_not_retryable():
    """InvalidURLError should not be retryable."""
    error = InvalidURLError("Malformed URL")
    assert error.retryable is False


def test_parse_error_is_not_retryable():
    """ParseError should not be retryable."""
    error = ParseError("Failed to parse HTML")
    assert error.retryable is False


def test_ssrf_blocked_error_is_not_retryable():
    """SSRFBlockedError should not be retryable."""
    error = SSRFBlockedError("Blocked IP: 127.0.0.1")
    assert error.retryable is False


def test_response_too_large_error_is_not_retryable():
    """ResponseTooLargeError should not be retryable."""
    error = ResponseTooLargeError("Response exceeds 10MB")
    assert error.retryable is False


def test_conversion_timeout_error_is_not_retryable():
    """ConversionTimeoutError should not be retryable."""
    error = ConversionTimeoutError("Conversion exceeded timeout")
    assert error.retryable is False
