"""Registry for rate limiter and cost tracker plugins."""

from __future__ import annotations

from typing import Callable, Dict, Any, Mapping

from .rate_limit import RateLimiter, NoopRateLimiter, FixedWindowRateLimiter, AdaptiveRateLimiter
from .cost_tracker import CostTracker, NoopCostTracker, FixedPriceCostTracker
from dmp.core.validation import ConfigurationError, validate_schema


class _Factory:
    def __init__(self, factory: Callable[[Dict[str, Any]], Any], schema: Mapping[str, Any] | None = None):
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(self, options: Dict[str, Any], *, context: str) -> Any:
        self.validate(options, context=context)
        return self.factory(options)


_rate_limiters: Dict[str, _Factory] = {
    "noop": _Factory(lambda options: NoopRateLimiter()),
    "fixed_window": _Factory(
        lambda options: FixedWindowRateLimiter(
            requests=int(options.get("requests", 1)),
            per_seconds=float(options.get("per_seconds", 1.0)),
        ),
        schema={
            "type": "object",
            "properties": {
                "requests": {"type": "integer", "minimum": 1},
                "per_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
            "additionalProperties": True,
        },
    ),
    "adaptive": _Factory(
        lambda options: AdaptiveRateLimiter(
            requests_per_minute=int(options.get("requests_per_minute", options.get("requests", 60)) or 60),
            tokens_per_minute=(lambda value: int(value) if value is not None else None)(options.get("tokens_per_minute")),
            interval_seconds=float(options.get("interval_seconds", 60.0)),
        ),
        schema={
            "type": "object",
            "properties": {
                "requests_per_minute": {"type": "integer", "minimum": 1},
                "requests": {"type": "integer", "minimum": 1},
                "tokens_per_minute": {"type": "integer", "minimum": 0},
                "interval_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
            "additionalProperties": True,
        },
    ),
}

_cost_trackers: Dict[str, _Factory] = {
    "noop": _Factory(lambda options: NoopCostTracker()),
    "fixed_price": _Factory(
        lambda options: FixedPriceCostTracker(
            prompt_token_price=float(options.get("prompt_token_price", 0.0)),
            completion_token_price=float(options.get("completion_token_price", 0.0)),
        ),
        schema={
            "type": "object",
            "properties": {
                "prompt_token_price": {"type": "number", "minimum": 0},
                "completion_token_price": {"type": "number", "minimum": 0},
            },
            "additionalProperties": True,
        },
    ),
}


def register_rate_limiter(name: str, factory: Callable[[Dict[str, Any]], RateLimiter]) -> None:
    _rate_limiters[name] = _Factory(factory)


def register_cost_tracker(name: str, factory: Callable[[Dict[str, Any]], CostTracker]) -> None:
    _cost_trackers[name] = _Factory(factory)


def create_rate_limiter(definition: Dict[str, Any] | None) -> RateLimiter | None:
    if not definition:
        return None
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {})
    if name not in _rate_limiters:
        raise ValueError(f"Unknown rate limiter plugin '{name}'")
    return _rate_limiters[name].create(options, context=f"rate_limiter:{name}")


def create_cost_tracker(definition: Dict[str, Any] | None) -> CostTracker | None:
    if not definition:
        return None
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {})
    if name not in _cost_trackers:
        raise ValueError(f"Unknown cost tracker plugin '{name}'")
    return _cost_trackers[name].create(options, context=f"cost_tracker:{name}")


def validate_rate_limiter(definition: Dict[str, Any] | None) -> None:
    if not definition:
        return
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {})
    if name not in _rate_limiters:
        raise ConfigurationError(f"Unknown rate limiter plugin '{name}'")
    _rate_limiters[name].validate(options, context=f"rate_limiter:{name}")


def validate_cost_tracker(definition: Dict[str, Any] | None) -> None:
    if not definition:
        return
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {})
    if name not in _cost_trackers:
        raise ConfigurationError(f"Unknown cost tracker plugin '{name}'")
    _cost_trackers[name].validate(options, context=f"cost_tracker:{name}")


__all__ = [
    "register_rate_limiter",
    "register_cost_tracker",
    "create_rate_limiter",
    "create_cost_tracker",
    "validate_rate_limiter",
    "validate_cost_tracker",
]
