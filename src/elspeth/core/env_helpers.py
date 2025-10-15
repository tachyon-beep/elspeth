"""Environment variable helpers with consistent error handling."""

import logging
import os

logger = logging.getLogger(__name__)


def require_env_var(env_var: str, strip: bool = True, error_msg: str | None = None) -> str:
    """Load required environment variable or raise error.

    Args:
        env_var: Environment variable name
        strip: Strip whitespace from value
        error_msg: Custom error message (default: "{env_var} not set")

    Returns:
        Environment variable value

    Raises:
        ValueError: If environment variable not set or empty

    Examples:
        >>> os.environ["AZURE_OPENAI_API_KEY"] = "test-key"
        >>> api_key = require_env_var("AZURE_OPENAI_API_KEY")
        >>> api_key
        'test-key'
    """
    value = os.getenv(env_var)
    if not value:
        msg = error_msg or f"Environment variable {env_var} not set"
        raise ValueError(msg)
    return value.strip() if strip else value


def get_env_var(
    env_var: str,
    default: str | None = None,
    strip: bool = True,
    warn_if_missing: bool = False,
) -> str | None:
    """Load optional environment variable with default.

    Args:
        env_var: Environment variable name
        default: Default value if not set
        strip: Strip whitespace from value
        warn_if_missing: Log warning if environment variable not set

    Returns:
        Environment variable value, default, or None

    Examples:
        >>> os.environ["DEPLOYMENT"] = "gpt-4"
        >>> deployment = get_env_var("DEPLOYMENT", default="gpt-3.5-turbo")
        >>> deployment
        'gpt-4'
        >>> optional = get_env_var("MISSING_VAR", default="fallback")
        >>> optional
        'fallback'
    """
    value = os.getenv(env_var)
    if not value:
        if warn_if_missing:
            logger.warning(f"Environment variable {env_var} not set")
        return default
    return value.strip() if strip else value


__all__ = ["require_env_var", "get_env_var"]
