"""AzureContentSafetyMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Sequence

import requests

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMMiddleware, LLMRequest
from elspeth.core.base.types import DeterminismLevel, SecurityLevel
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


class AzureContentSafetyMiddleware(BasePlugin, LLMMiddleware):
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
        retry_attempts: int = 3,
    ) -> None:
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True,  # ADR-002-B: Immutable policy
        )
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
        # Configure bounded retry attempts for Content Safety calls
        try:
            self.retry_attempts = max(1, int(retry_attempts))
        except (ValueError, TypeError):
            self.retry_attempts = 3

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
        # Best-effort, bounded retries with exponential backoff + jitter
        attempts, delay = 0, 0.5
        while True:
            attempts += 1
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                response.raise_for_status()
                break
            except requests.RequestException:  # pragma: no cover - network failure/backoff path
                if attempts >= self.retry_attempts:
                    raise
                # Non-cryptographic jitter: safe for backoff; avoids thundering herd.
                # Disable jitter for high/guaranteed determinism to preserve reproducibility.
                det = getattr(self, "_elspeth_determinism_level", getattr(self, "determinism_level", None))
                deterministic = False
                if isinstance(det, DeterminismLevel):
                    deterministic = det in (DeterminismLevel.HIGH, DeterminismLevel.GUARANTEED)
                elif isinstance(det, str):
                    deterministic = det.lower() in ("high", "guaranteed")
                jitter = 0.0 if deterministic else (random.random() * 0.2)  # NOSONAR # noqa: S311 - non-crypto jitter is acceptable
                time.sleep(delay + jitter)
                delay *= 2
        data = response.json()
        flagged = False
        max_severity = 0
        for item in data.get("results", data.get("categories", [])):
            severity = int(item.get("severity", 0))
            max_severity = max(max_severity, severity)
            if severity >= self.threshold:
                flagged = True
        return {"flagged": flagged, "max_severity": max_severity, "raw": data}


def _create_azure_content_safety_middleware(options: dict[str, Any], context: PluginContext) -> AzureContentSafetyMiddleware:
    """Factory for Azure Content Safety middleware (ADR-002-B: security policy is immutable)."""
    opts = dict(options)
    # ADR-002-B: security_level is hard-coded in plugin, not passed as parameter
    return AzureContentSafetyMiddleware(
        endpoint=str(opts.get("endpoint", "")),
        key=str(opts.get("key")) if opts.get("key") is not None else None,
        key_env=str(opts.get("key_env")) if opts.get("key_env") is not None else None,
        api_version=str(opts.get("api_version")) if opts.get("api_version") is not None else None,
        categories=opts.get("categories"),
        severity_threshold=int(opts.get("severity_threshold", 4)),
        on_violation=opts.get("on_violation", "abort"),
        mask=opts.get("mask", "[CONTENT BLOCKED]"),
        channel=opts.get("channel"),
        on_error=opts.get("on_error", "abort"),
    )


register_middleware(
    "azure_content_safety",
    _create_azure_content_safety_middleware,
    schema=_CONTENT_SAFETY_SCHEMA,
)


__all__ = ["AzureContentSafetyMiddleware"]
