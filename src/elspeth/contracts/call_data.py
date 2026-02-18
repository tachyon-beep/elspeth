"""Frozen dataclasses for LLM and HTTP call audit data.

Replaces loose ``dict[str, Any]`` at 23+ construction sites with typed,
immutable value objects that produce hash-stable dicts via ``to_dict()``.
Follows the ``TokenUsage`` precedent (commit dffe74a6).

Trust-tier notes
----------------
* Construction — used by our code (Tier 1/2).
* ``to_dict()`` — serialization boundary, produces identical dicts to
  the old inline dict construction for hash stability.
* ``raw_response`` on ``LLMCallResponse`` is intentionally ``dict[str, Any]``
  because it's Tier 3 SDK data that varies across providers/versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from elspeth.contracts.token_usage import TokenUsage

# ---------------------------------------------------------------------------
# LLM call data
# ---------------------------------------------------------------------------

_LLM_REQUEST_RESERVED_KEYS = frozenset(
    {"model", "messages", "temperature", "provider", "max_tokens"},
)


@dataclass(frozen=True, slots=True)
class LLMCallRequest:
    """Audit record for an outbound LLM API request."""

    model: str
    messages: list[dict[str, Any]]
    temperature: float
    provider: str
    max_tokens: int | None = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if collisions := (_LLM_REQUEST_RESERVED_KEYS & self.extra_kwargs.keys()):
            msg = f"extra_kwargs contains reserved key(s) that would overwrite audit fields: {collisions}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Conditionally omits ``max_tokens`` when None, spreads
        ``extra_kwargs`` to match the old ``**kwargs`` pattern.
        """
        d: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "provider": self.provider,
            **self.extra_kwargs,
        }
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        return d


@dataclass(frozen=True, slots=True)
class LLMCallResponse:
    """Audit record for an LLM API response."""

    content: str
    model: str
    usage: TokenUsage
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Calls ``self.usage.to_dict()`` for the usage field.
        """
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage.to_dict(),
            "raw_response": self.raw_response,
        }


@dataclass(frozen=True, slots=True)
class LLMCallError:
    """Audit record for an LLM API error."""

    type: str
    message: str
    retryable: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        All fields always present (retryable is never optional).
        """
        return {
            "type": self.type,
            "message": self.message,
            "retryable": self.retryable,
        }


# ---------------------------------------------------------------------------
# HTTP call data
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HTTPCallRequest:
    """Audit record for an outbound HTTP request.

    Handles three request shapes:

    * **Standard** (``resolved_ip`` is None): includes json/params by method.
    * **SSRF-safe** (``resolved_ip`` set, no hop): includes resolved_ip.
    * **Redirect hop** (``hop_number`` set): includes hop tracking fields.
    """

    method: str
    url: str
    headers: dict[str, str]
    json: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    resolved_ip: str | None = None
    hop_number: int | None = None
    redirect_from: str | None = None

    def __post_init__(self) -> None:
        if self.hop_number is not None and self.resolved_ip is None:
            msg = "hop_number requires resolved_ip (redirect hops are always SSRF-safe)"
            raise ValueError(msg)
        if self.redirect_from is not None and self.hop_number is None:
            msg = "redirect_from requires hop_number"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Standard path (``resolved_ip`` is None) includes json/params by
        method.  SSRF/redirect path skips json/params and includes
        resolved_ip and hop tracking fields.
        """
        d: dict[str, Any] = {"method": self.method, "url": self.url}
        if self.resolved_ip is not None:
            d["resolved_ip"] = self.resolved_ip
        if self.hop_number is not None:
            d["hop_number"] = self.hop_number
        if self.redirect_from is not None:
            d["redirect_from"] = self.redirect_from
        d["headers"] = self.headers
        # Standard path only: include method-specific body/params
        if self.resolved_ip is None:
            if self.method == "POST":
                d["json"] = self.json
            elif self.method == "GET":
                d["params"] = self.params
        return d


@dataclass(frozen=True, slots=True)
class HTTPCallResponse:
    """Audit record for an HTTP response.

    Redirect hop responses omit ``body_size`` and ``body`` (only
    ``status_code`` and ``headers`` are meaningful for intermediate hops).
    """

    status_code: int
    headers: dict[str, str]
    body_size: int | None = None
    body: dict[str, Any] | str | None = None
    redirect_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Includes ``body_size``/``body`` when ``body_size`` is not None.
        Includes ``redirect_count`` when > 0.
        """
        d: dict[str, Any] = {
            "status_code": self.status_code,
            "headers": self.headers,
        }
        if self.body_size is not None:
            d["body_size"] = self.body_size
            d["body"] = self.body
        if self.redirect_count > 0:
            d["redirect_count"] = self.redirect_count
        return d


@dataclass(frozen=True, slots=True)
class HTTPCallError:
    """Audit record for an HTTP error.

    Network errors (timeout, connection refused) omit ``status_code``.
    HTTP errors (4xx/5xx) include ``status_code``.
    """

    type: str
    message: str
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Includes ``status_code`` only when not None.
        """
        d: dict[str, Any] = {
            "type": self.type,
            "message": self.message,
        }
        if self.status_code is not None:
            d["status_code"] = self.status_code
        return d
