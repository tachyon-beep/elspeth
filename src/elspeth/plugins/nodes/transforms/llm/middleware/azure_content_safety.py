"""AzureContentSafetyMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
import os
from typing import Any, Sequence

import requests

from elspeth.core.protocols import LLMMiddleware, LLMRequest
from elspeth.core.registries.middleware import register_middleware

logger = logging.getLogger(__name__)

_CONTENT_SAFETY_SCHEMA = {
    "type": "object",
    "properties": {
        "endpoint": {"type": "string"},
        "key": {"type": "string"},
        "key_env": {"type": "string"},
        "api_version": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "severity_threshold": {"type": "integer", "minimum": 0, "maximum": 7},
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "mask": {"type": "string"},
        "channel": {"type": "string"},
        "on_error": {"type": "string", "enum": ["abort", "skip"]},
    },
    "required": ["endpoint"],
    "additionalProperties": True,
}


class AzureContentSafetyMiddleware(LLMMiddleware):
    """Use Azure Content Safety service to screen prompts before submission."""

    name = "azure_content_safety"

    def __init__(
        self,
        *,
        endpoint: str,
        key: str | None = None,
        key_env: str | None = None,
        api_version: str | None = None,
        categories: Sequence[str] | None = None,
        severity_threshold: int = 4,
        on_violation: str = "abort",
        mask: str = "[CONTENT BLOCKED]",
        channel: str | None = None,
        on_error: str = "abort",
    ) -> None:
        if not endpoint:
            raise ValueError("Azure Content Safety requires an endpoint")
        self.endpoint = endpoint.rstrip("/")
        key_value = key or (os.environ.get(key_env) if key_env else None)
        if not key_value:
            raise ValueError("Azure Content Safety requires an API key or key_env")
        self.key = key_value
        self.api_version = api_version or "2023-10-01"
        self.categories = list(categories or ["Hate", "Violence", "SelfHarm", "Sexual"])
        self.threshold = max(0, min(int(severity_threshold), 7))
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.mask = mask
        self.channel = channel or "elspeth.azure_content_safety"
        handler = (on_error or "abort").lower()
        if handler not in {"abort", "skip"}:
            handler = "abort"
        self.on_error = handler

    def before_request(self, request: LLMRequest) -> LLMRequest:
        try:
            result = self._analyze_text(request.user_prompt)
        except Exception as exc:  # pragma: no cover - network failure path
            if self.on_error == "skip":
                logger.warning("[%s] Content Safety call failed; skipping (%s)", self.channel, exc)
                return request
            raise

        if result.get("flagged"):
            logger.warning("[%s] Prompt flagged by Azure Content Safety: %s", self.channel, result)
            if self.mode == "abort":
                raise ValueError("Prompt blocked by Azure Content Safety")
            if self.mode == "mask":
                return request.clone(user_prompt=self.mask)
        return request

    def _analyze_text(self, text: str) -> dict[str, Any]:
        url = f"{self.endpoint}/contentsafety/text:analyze?api-version={self.api_version}"
        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.key,
        }
        payload = {
            "text": text,
            "categories": self.categories,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        flagged = False
        max_severity = 0
        for item in data.get("results", data.get("categories", [])):
            severity = int(item.get("severity", 0))
            max_severity = max(max_severity, severity)
            if severity >= self.threshold:
                flagged = True
        return {"flagged": flagged, "max_severity": max_severity, "raw": data}


register_middleware(
    "azure_content_safety",
    lambda options, context: AzureContentSafetyMiddleware(
        endpoint=str(options.get("endpoint", "")),
        key=str(options.get("key")) if options.get("key") is not None else None,
        key_env=str(options.get("key_env")) if options.get("key_env") is not None else None,
        api_version=str(options.get("api_version")) if options.get("api_version") is not None else None,
        categories=options.get("categories"),
        severity_threshold=int(options.get("severity_threshold", 4)),
        on_violation=options.get("on_violation", "abort"),
        mask=options.get("mask", "[CONTENT BLOCKED]"),
        channel=options.get("channel"),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_CONTENT_SAFETY_SCHEMA,
)


__all__ = ["AzureContentSafetyMiddleware"]
