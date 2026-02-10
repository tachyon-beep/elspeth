"""Regression tests for reserved connection names in settings validators."""

import pytest
from pydantic import ValidationError

from elspeth.core.config import (
    AggregationSettings,
    GateSettings,
    SourceSettings,
    TransformSettings,
    TriggerConfig,
)


def test_source_on_success_rejects_reserved_continue() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        SourceSettings(
            plugin="csv",
            on_success="continue",
        )


def test_transform_input_rejects_reserved_continue() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        TransformSettings(
            name="t1",
            plugin="passthrough",
            input="continue",
        )


def test_transform_input_rejects_reserved_fork() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        TransformSettings(
            name="t1",
            plugin="passthrough",
            input="fork",
        )


def test_transform_on_success_rejects_reserved_continue() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        TransformSettings(
            name="t1",
            plugin="passthrough",
            input="in_conn",
            on_success="continue",
        )


def test_gate_input_rejects_reserved_continue() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        GateSettings(
            name="g1",
            input="continue",
            condition="row['label']",
            routes={"high": "sink_a"},
        )


def test_aggregation_input_rejects_reserved_continue() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        AggregationSettings(
            name="agg1",
            plugin="batch_stats",
            input="continue",
            trigger=TriggerConfig(count=10),
        )


def test_aggregation_on_success_rejects_reserved_continue() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        AggregationSettings(
            name="agg1",
            plugin="batch_stats",
            input="agg_in",
            on_success="continue",
            trigger=TriggerConfig(count=10),
        )
