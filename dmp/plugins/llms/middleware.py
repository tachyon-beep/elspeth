"""Default LLM middleware implementations."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, Sequence

import requests

from dmp.core.llm.middleware import LLMMiddleware, LLMRequest
from dmp.core.llm.registry import register_middleware

logger = logging.getLogger(__name__)


_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "include_prompts": {"type": "boolean"},
        "channel": {"type": "string"},
    },
    "additionalProperties": True,
}

_PROMPT_SHIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "denied_terms": {"type": "array", "items": {"type": "string"}},
        "mask": {"type": "string"},
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "channel": {"type": "string"},
    },
    "additionalProperties": True,
}

_HEALTH_SCHEMA = {
    "type": "object",
    "properties": {
        "heartbeat_interval": {"type": "number", "minimum": 0.0},
        "stats_window": {"type": "integer", "minimum": 1},
        "channel": {"type": "string"},
        "include_latency": {"type": "boolean"},
    },
    "additionalProperties": True,
}

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


class AuditMiddleware(LLMMiddleware):
    name = "audit_logger"

    def __init__(self, *, include_prompts: bool = False, channel: str | None = None):
        self.include_prompts = include_prompts
        self.channel = channel or "dmp.audit"

    def before_request(self, request: LLMRequest) -> LLMRequest:
        payload = {"metadata": request.metadata}
        if self.include_prompts:
            payload.update({"system": request.system_prompt, "user": request.user_prompt})
        logger.info("[%s] LLM request metadata=%s", self.channel, payload)
        return request

    def after_response(self, request: LLMRequest, response: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("[%s] LLM response metrics=%s", self.channel, response.get("metrics"))
        if self.include_prompts:
            logger.debug("[%s] LLM response content=%s", self.channel, response.get("content"))
        return response


class PromptShieldMiddleware(LLMMiddleware):
    name = "prompt_shield"

    def __init__(
        self,
        *,
        denied_terms: Sequence[str] | None = None,
        mask: str = "[REDACTED]",
        on_violation: str = "abort",
        channel: str | None = None,
    ):
        self.denied_terms = [term.lower() for term in denied_terms or []]
        self.mask = mask
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.channel = channel or "dmp.prompt_shield"

    def before_request(self, request: LLMRequest) -> LLMRequest:
        lowered = request.user_prompt.lower()
        for term in self.denied_terms:
            if term and term in lowered:
                logger.warning("[%s] Prompt contains blocked term '%s'", self.channel, term)
                if self.mode == "abort":
                    raise ValueError(f"Prompt contains blocked term '{term}'")
                if self.mode == "mask":
                    masked = request.user_prompt.replace(term, self.mask)
                    return request.clone(user_prompt=masked)
                break
        return request


class HealthMonitorMiddleware(LLMMiddleware):
    """Emit heartbeat logs summarising middleware activity."""

    name = "health_monitor"

    def __init__(
        self,
        *,
        heartbeat_interval: float = 60.0,
        stats_window: int = 50,
        channel: str | None = None,
        include_latency: bool = True,
    ) -> None:
        if heartbeat_interval < 0:
            raise ValueError("heartbeat_interval must be non-negative")
        self.interval = float(heartbeat_interval)
        self.window = max(int(stats_window), 1)
        self.channel = channel or "dmp.health"
        self.include_latency = include_latency
        self._lock = threading.Lock()
        self._latencies: deque[float] = deque(maxlen=self.window)
        self._inflight: Dict[int, float] = {}
        self._total_requests = 0
        self._total_failures = 0
        self._last_heartbeat = time.monotonic()

    def before_request(self, request: LLMRequest) -> LLMRequest:
        start = time.monotonic()
        with self._lock:
            self._inflight[id(request)] = start
        return request

    def after_response(self, request: LLMRequest, response: Dict[str, Any]) -> Dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            start = self._inflight.pop(id(request), None)
            self._total_requests += 1
            if isinstance(response, dict) and response.get("error"):
                self._total_failures += 1
            if start is not None and self.include_latency:
                self._latencies.append(now - start)
            if self.interval == 0 or now - self._last_heartbeat >= self.interval:
                self._emit(now)
        return response

    def _emit(self, now: float) -> None:
        data: Dict[str, Any] = {
            "requests": self._total_requests,
            "failures": self._total_failures,
        }
        if self._total_requests:
            data["failure_rate"] = self._total_failures / self._total_requests
        if self.include_latency and self._latencies:
            latencies = list(self._latencies)
            count = len(latencies)
            total = sum(latencies)
            data.update(
                {
                    "latency_count": count,
                    "latency_avg": total / count,
                    "latency_min": min(latencies),
                    "latency_max": max(latencies),
                }
            )
        logger.info("[%s] health heartbeat %s", self.channel, data)
        self._last_heartbeat = now


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
        self.channel = channel or "dmp.azure_content_safety"
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

    def _analyze_text(self, text: str) -> Dict[str, Any]:
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
    "audit_logger",
    lambda options: AuditMiddleware(
        include_prompts=bool(options.get("include_prompts", False)),
        channel=options.get("channel"),
    ),
    schema=_AUDIT_SCHEMA,
)

register_middleware(
    "prompt_shield",
    lambda options: PromptShieldMiddleware(
        denied_terms=options.get("denied_terms", []),
        mask=options.get("mask", "[REDACTED]"),
        on_violation=options.get("on_violation", "abort"),
        channel=options.get("channel"),
    ),
    schema=_PROMPT_SHIELD_SCHEMA,
)

register_middleware(
    "health_monitor",
    lambda options: HealthMonitorMiddleware(
        heartbeat_interval=float(options.get("heartbeat_interval", 60.0)),
        stats_window=int(options.get("stats_window", 50)),
        channel=options.get("channel"),
        include_latency=bool(options.get("include_latency", True)),
    ),
    schema=_HEALTH_SCHEMA,
)

register_middleware(
    "azure_content_safety",
    lambda options: AzureContentSafetyMiddleware(
        endpoint=options.get("endpoint"),
        key=options.get("key"),
        key_env=options.get("key_env"),
        api_version=options.get("api_version"),
        categories=options.get("categories"),
        severity_threshold=int(options.get("severity_threshold", 4)),
        on_violation=options.get("on_violation", "abort"),
        mask=options.get("mask", "[CONTENT BLOCKED]"),
        channel=options.get("channel"),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_CONTENT_SAFETY_SCHEMA,
)


__all__ = ["AuditMiddleware", "PromptShieldMiddleware", "HealthMonitorMiddleware", "AzureContentSafetyMiddleware"]
