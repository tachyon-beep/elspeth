"""Registry for rate limiter and cost tracker plugins."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping

from elspeth.core.security import coalesce_security_level
from elspeth.core.validation import ConfigurationError, validate_schema

from .cost_tracker import CostTracker, FixedPriceCostTracker, NoopCostTracker
from .rate_limit import AdaptiveRateLimiter, FixedWindowRateLimiter, NoopRateLimiter, RateLimiter


class _Factory:
    """Wrap plugin constructors with optional schema validation."""

    def __init__(self, factory: Callable[[Dict[str, Any]], Any], schema: Mapping[str, Any] | None = None):
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        """Validate option dictionaries using the provided schema."""

        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(self, options: Dict[str, Any], *, context: str) -> Any:
        """Validate and instantiate the plugin with `options`."""

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
    """Register a custom rate limiter factory under the given name."""

    _rate_limiters[name] = _Factory(factory)


def register_cost_tracker(name: str, factory: Callable[[Dict[str, Any]], CostTracker]) -> None:
    """Register a custom cost tracker factory under the given name."""

    _cost_trackers[name] = _Factory(factory)


def create_rate_limiter(definition: Dict[str, Any] | None) -> RateLimiter | None:
    """Instantiate a rate limiter from a configuration dictionary."""

    if not definition:
        return None
    name = definition.get("plugin") or definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _rate_limiters:
        raise ValueError(f"Unknown rate limiter plugin '{name}'")
    try:
        level = coalesce_security_level(definition.get("security_level"), options.pop("security_level", None))
    except ValueError as exc:
        raise ConfigurationError(f"rate_limiter:{name}: {exc}") from exc
    limiter = _rate_limiters[name].create(options, context=f"rate_limiter:{name}")
    setattr(limiter, "_elspeth_security_level", level)
    return limiter


def create_cost_tracker(definition: Dict[str, Any] | None) -> CostTracker | None:
    """Instantiate a cost tracker from a configuration dictionary."""

    if not definition:
        return None
    name = definition.get("plugin") or definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _cost_trackers:
        raise ValueError(f"Unknown cost tracker plugin '{name}'")
    try:
        level = coalesce_security_level(definition.get("security_level"), options.pop("security_level", None))
    except ValueError as exc:
        raise ConfigurationError(f"cost_tracker:{name}: {exc}") from exc
    tracker = _cost_trackers[name].create(options, context=f"cost_tracker:{name}")
    setattr(tracker, "_elspeth_security_level", level)
    return tracker


def validate_rate_limiter(definition: Dict[str, Any] | None) -> None:
    """Validate a rate limiter definition without instantiating it."""

    if not definition:
        return
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {})
    if name not in _rate_limiters:
        raise ConfigurationError(f"Unknown rate limiter plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Rate limiter options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"rate_limiter:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _rate_limiters[name].validate(prepared, context=f"rate_limiter:{name}")


def validate_cost_tracker(definition: Dict[str, Any] | None) -> None:
    """Validate a cost tracker definition without instantiation."""

    if not definition:
        return
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {})
    if name not in _cost_trackers:
        raise ConfigurationError(f"Unknown cost tracker plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Cost tracker options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"cost_tracker:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _cost_trackers[name].validate(prepared, context=f"cost_tracker:{name}")


__all__ = [
    "register_rate_limiter",
    "register_cost_tracker",
    "create_rate_limiter",
    "create_cost_tracker",
    "validate_rate_limiter",
    "validate_cost_tracker",
]
