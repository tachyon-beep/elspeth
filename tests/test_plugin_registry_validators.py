from contextlib import contextmanager

import pytest

from elspeth.core.experiments.experiment_registries import (
    aggregation_plugin_registry,
    baseline_plugin_registry,
    row_plugin_registry,
    validation_plugin_registry,
)
from elspeth.core.experiments.plugin_registry import (
    create_row_plugin,
    validate_aggregation_plugin_definition,
    validate_baseline_plugin_definition,
    validate_row_plugin_definition,
    validate_validation_plugin_definition,
)
from elspeth.core.registries import middleware as middleware_module
from elspeth.core.registries.middleware import validate_middleware_definition
from elspeth.core.validation import ConfigurationError


@contextmanager
def registered(registry, name, factory):
    registry.register(name, factory, schema=None)
    try:
        yield
    finally:
        registry.unregister(name)


@contextmanager
def registered_middleware(name, factory):
    middleware_module.register_middleware(name, factory)
    try:
        yield
    finally:
        middleware_module._middleware_registry.unregister(name)


def test_validate_row_plugin_definition_accepts_registered_plugin():
    def factory(options, context):
        class Plugin:
            name = "row"

            def process_row(self, row, responses):
                return {}

        return Plugin()

    with registered(row_plugin_registry, "row_validator", factory):
        validate_row_plugin_definition({"name": "row_validator", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})


def test_validate_row_plugin_definition_missing_name_raises():
    with pytest.raises(ConfigurationError):
        validate_row_plugin_definition({})


def test_validate_row_plugin_definition_rejects_non_mapping_options():
    with pytest.raises(ConfigurationError):
        validate_row_plugin_definition(
            {
                "name": "bad",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": "not-a-dict",
            }
        )


def test_validate_aggregation_plugin_definition_accepts_registered_plugin():
    def factory(options, context):
        class Plugin:
            name = "agg"

            def finalize(self, records):
                return {}

        return Plugin()

    with registered(aggregation_plugin_registry, "agg_validator", factory):
        validate_aggregation_plugin_definition({"name": "agg_validator", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})


def test_validate_aggregation_plugin_definition_conflicting_security_raises():
    with pytest.raises(ConfigurationError):
        validate_aggregation_plugin_definition(
            {
                "name": "agg_validator",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"security_level": "UNOFFICIAL"},
            }
        )


def test_validate_baseline_plugin_definition_accepts_registered_plugin():
    def factory(options, context):
        class Plugin:
            name = "baseline"

            def compute(self, *args, **kwargs):  # pragma: no cover - interface placeholder
                return {}

        return Plugin()

    with registered(baseline_plugin_registry, "baseline_validator", factory):
        validate_baseline_plugin_definition({"name": "baseline_validator", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})


def test_validate_validation_plugin_definition_accepts_registered_plugin():
    def factory(options, context):
        class Plugin:
            name = "validator"

            def validate(self, results):
                return []

        return Plugin()

    with registered(validation_plugin_registry, "validation_validator", factory):
        validate_validation_plugin_definition(
            {"name": "validation_validator", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}
        )


def test_create_row_plugin_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown row experiment plugin"):
        create_row_plugin({"name": "ghost", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})


def test_validate_middleware_definition_accepts_registered_plugin():
    def factory(options, context):
        class Middleware:
            name = "middleware"

            def before_request(self, request):  # pragma: no cover - interface placeholder
                return request

        return Middleware()

    with registered_middleware("middleware_validator", factory):
        validate_middleware_definition({"name": "middleware_validator", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})


def test_validate_middleware_definition_unknown_plugin_raises():
    with pytest.raises(ConfigurationError, match="Unknown LLM middleware"):
        validate_middleware_definition({"name": "missing"})
