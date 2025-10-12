"""Registry for rate limiter and cost tracker plugins."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterable, Mapping

from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.security import coalesce_security_level
from elspeth.core.validation import ConfigurationError, validate_schema

from .cost_tracker import CostTracker, FixedPriceCostTracker, NoopCostTracker
from .rate_limit import AdaptiveRateLimiter, FixedWindowRateLimiter, NoopRateLimiter, RateLimiter


def _create_adaptive_rate_limiter(options: Dict[str, Any]) -> AdaptiveRateLimiter:
    """Build an adaptive rate limiter using validated option defaults."""

    requests_per_minute = int(options.get("requests_per_minute", options.get("requests", 60)) or 60)
    token_value = options.get("tokens_per_minute")
    tokens_per_minute = int(token_value) if token_value is not None else None
    interval_seconds = float(options.get("interval_seconds", 60.0))
    return AdaptiveRateLimiter(
        requests_per_minute=requests_per_minute,
        tokens_per_minute=tokens_per_minute,
        interval_seconds=interval_seconds,
    )


class _Factory:
    """Wrap plugin constructors with optional schema validation."""

    def __init__(
        self,
        factory: Callable[[Dict[str, Any], PluginContext], Any],
        schema: Mapping[str, Any] | None = None,
    ):
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        """Validate option dictionaries using the provided schema."""

        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(
        self,
        options: Dict[str, Any],
        *,
        plugin_context: PluginContext,
        schema_context: str,
    ) -> Any:
        """Validate and instantiate the plugin with `options`."""

        self.validate(options, context=schema_context)
        return self.factory(options, plugin_context)


_rate_limiters: Dict[str, _Factory] = {
    "noop": _Factory(lambda options, context: NoopRateLimiter()),
    "fixed_window": _Factory(
        lambda options, context: FixedWindowRateLimiter(
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
        lambda options, context: _create_adaptive_rate_limiter(options),
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
    "noop": _Factory(lambda options, context: NoopCostTracker()),
    "fixed_price": _Factory(
        lambda options, context: FixedPriceCostTracker(
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


def register_rate_limiter(name: str, factory: Callable[..., RateLimiter]) -> None:
    """Register a custom rate limiter factory under the given name."""

    signature = inspect.signature(factory)

    if len(signature.parameters) == 1:

        def _wrapped(options: Dict[str, Any], _context: PluginContext) -> RateLimiter:
            return factory(options)

        _rate_limiters[name] = _Factory(_wrapped)
    else:
        _rate_limiters[name] = _Factory(factory)  # type: ignore[arg-type]


def register_cost_tracker(name: str, factory: Callable[..., CostTracker]) -> None:
    """Register a custom cost tracker factory under the given name."""

    signature = inspect.signature(factory)

    if len(signature.parameters) == 1:

        def _wrapped(options: Dict[str, Any], _context: PluginContext) -> CostTracker:
            return factory(options)

        _cost_trackers[name] = _Factory(_wrapped)
    else:
        _cost_trackers[name] = _Factory(factory)  # type: ignore[arg-type]


def create_rate_limiter(
    definition: Dict[str, Any] | None,
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> RateLimiter | None:
    """Instantiate a rate limiter from a configuration dictionary."""

    if not definition:
        return None
    name = definition.get("plugin") or definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _rate_limiters:
        raise ValueError(f"Unknown rate limiter plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"rate_limiter:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"rate_limiter:{name}.options.security_level")
    if provenance:
        sources.extend(provenance)
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"rate_limiter:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance_sources = tuple(sources or (f"rate_limiter:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="rate_limiter",
            security_level=level,
            provenance=provenance_sources,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="rate_limiter",
            security_level=level,
            provenance=provenance_sources,
        )
    limiter = _rate_limiters[name].create(
        payload,
        plugin_context=context,
        schema_context=f"rate_limiter:{name}",
    )
    apply_plugin_context(limiter, context)
    return limiter


def create_cost_tracker(
    definition: Dict[str, Any] | None,
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> CostTracker | None:
    """Instantiate a cost tracker from a configuration dictionary."""

    if not definition:
        return None
    name = definition.get("plugin") or definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _cost_trackers:
        raise ValueError(f"Unknown cost tracker plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"cost_tracker:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"cost_tracker:{name}.options.security_level")
    if provenance:
        sources.extend(provenance)
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"cost_tracker:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance_sources = tuple(sources or (f"cost_tracker:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="cost_tracker",
            security_level=level,
            provenance=provenance_sources,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="cost_tracker",
            security_level=level,
            provenance=provenance_sources,
        )
    tracker = _cost_trackers[name].create(
        payload,
        plugin_context=context,
        schema_context=f"cost_tracker:{name}",
    )
    apply_plugin_context(tracker, context)
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
