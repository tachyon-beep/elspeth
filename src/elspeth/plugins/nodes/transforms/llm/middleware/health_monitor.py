"""HealthMonitorMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMMiddleware, LLMRequest
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.middleware import register_middleware

logger = logging.getLogger(__name__)

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


class HealthMonitorMiddleware(BasePlugin, LLMMiddleware):
    """Emit heartbeat logs summarising middleware activity.

    Args:
        heartbeat_interval: Seconds between heartbeat emissions (default: 60.0).
        stats_window: Number of recent requests to track for statistics (default: 50).
        channel: Logger channel name (default: 'elspeth.health').
        include_latency: Whether to include latency stats in heartbeat (default: True).
    """

    name = "health_monitor"

    def __init__(
        self,
        *,
        heartbeat_interval: float = 60.0,
        stats_window: int = 50,
        channel: str | None = None,
        include_latency: bool = True,
    ) -> None:
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True,  # ADR-002-B: Immutable policy
        )
        if heartbeat_interval < 0:
            raise ValueError("heartbeat_interval must be non-negative")
        self.interval = float(heartbeat_interval)
        self.window = max(int(stats_window), 1)
        self.channel = channel or "elspeth.health"
        self.include_latency = include_latency
        self._lock = threading.Lock()
        self._latencies: deque[float] = deque(maxlen=self.window)
        self._inflight: dict[int, float] = {}
        self._total_requests = 0
        self._total_failures = 0
        self._last_heartbeat = time.monotonic()

    def before_request(self, request: LLMRequest) -> LLMRequest:
        start = time.monotonic()
        with self._lock:
            self._inflight[id(request)] = start
        return request

    def after_response(self, request: LLMRequest, response: dict[str, Any]) -> dict[str, Any]:
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
        data: dict[str, Any] = {
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


def _create_health_monitor_middleware(options: dict[str, Any], context: PluginContext) -> HealthMonitorMiddleware:
    """Factory for health monitor middleware (ADR-002-B: security policy is immutable)."""
    opts = dict(options)
    # ADR-002-B: security_level is hard-coded in plugin, not passed as parameter
    return HealthMonitorMiddleware(
        heartbeat_interval=float(opts.get("heartbeat_interval", 60.0)),
        stats_window=int(opts.get("stats_window", 50)),
        channel=opts.get("channel"),
        include_latency=bool(opts.get("include_latency", True)),
    )


register_middleware(
    "health_monitor",
    _create_health_monitor_middleware,
    schema=_HEALTH_SCHEMA,
)


__all__ = ["HealthMonitorMiddleware"]
