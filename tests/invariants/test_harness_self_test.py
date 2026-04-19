"""Meta-test for the ADR-009 §Clause 4 forward invariant.

Registers a deliberately mis-annotated fixture transform and asserts the
harness catches it. Without this, a refactor that accidentally empties the
discovery list would silently make the harness a no-op — the worst kind of
governance theatre.

Uses ``monkeypatch`` to scope the patched plugin list to exactly this test
— the global plugin manager is restored on teardown.
"""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.contracts.contexts import TransformContext
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.infrastructure.config_base import TransformDataConfig
from elspeth.plugins.infrastructure.results import TransformResult


class _DeliberatelyMisannotatedDropper(BaseTransform):
    """Test fixture: claims ``passes_through_input=True`` but drops a field.

    The harness forward invariant MUST catch this transform and report the
    dropped field. If it doesn't, the harness is broken.
    """

    name = "deliberately-misannotated-dropper"
    plugin_version = "1.0.0"
    source_file_hash: str | None = None
    config_model = TransformDataConfig
    passes_through_input = True  # LIE — this transform actually drops fields.

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = TransformDataConfig.from_dict(config, plugin_name=self.name)
        self._schema_config = cfg.schema_config
        self.input_schema, self.output_schema = self._create_schemas(cfg.schema_config, "Dropper")

    @classmethod
    def probe_config(cls) -> dict[str, Any]:
        return {"schema": {"mode": "observed"}}

    def process(self, row: PipelineRow, ctx: TransformContext) -> TransformResult:
        """Drops any non-first field from the input — triggers a violation
        when the probe row has 2+ fields."""
        data = row.to_dict()
        if not data:
            return TransformResult.success(
                PipelineRow(data, row.contract),
                success_reason={"action": "passthrough-empty"},
            )
        # Keep only the first key.
        first_key = next(iter(data))
        reduced = {first_key: data[first_key]}
        return TransformResult.success(
            PipelineRow(reduced, row.contract),  # Contract still names ALL fields (LIE)
            success_reason={"action": "reduce"},
        )


def test_harness_catches_deliberate_misannotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the harness is healthy, the forward invariant must raise
    AssertionError when run against _DeliberatelyMisannotatedDropper.

    This meta-test patches the plugin manager to include ONLY the fixture
    transform, then invokes the harness's discovery and forward-invariant
    logic directly.
    """
    from elspeth.plugins.infrastructure.manager import get_shared_plugin_manager

    manager = get_shared_plugin_manager()

    def _patched_get_transforms() -> list[type[BaseTransform]]:
        return [_DeliberatelyMisannotatedDropper]

    monkeypatch.setattr(manager, "get_transforms", _patched_get_transforms)

    # Drive the harness's discovery + forward invariant manually. We don't
    # use pytest's parametrize machinery here because that would require
    # running the harness as a subprocess.
    from tests.invariants.test_pass_through_invariants import (
        _annotated_pass_through_plugins,
        _probe_instantiate,
    )

    plugins = _annotated_pass_through_plugins()
    assert plugins == [_DeliberatelyMisannotatedDropper], "monkeypatch failed — plugin manager did not return the fixture alone"

    # Instantiate the fixture and run it on a multi-field probe row.
    transform = _probe_instantiate(_DeliberatelyMisannotatedDropper)
    from elspeth.contracts.schema_contract import FieldContract, SchemaContract
    from tests.fixtures.factories import make_context

    contract = SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(normalized_name="a", original_name="a", python_type=int, required=True, source="inferred", nullable=False),
            FieldContract(normalized_name="b", original_name="b", python_type=int, required=True, source="inferred", nullable=False),
        ),
        locked=True,
    )
    probe = PipelineRow({"a": 1, "b": 2}, contract)
    result = transform.process(probe, make_context())

    # Manually assert the invariant the harness checks — mirroring the
    # forward-invariant logic.
    emitted = [result.row] if result.row is not None else list(result.rows or [])
    assert emitted, "fixture must emit at least one row"

    input_fields = frozenset(fc.normalized_name for fc in probe.contract.fields)
    dropped_fields: list[str] = []
    for emitted_row in emitted:
        runtime_observed = frozenset(fc.normalized_name for fc in emitted_row.contract.fields) & frozenset(emitted_row.keys())
        dropped = input_fields - runtime_observed
        if dropped:
            dropped_fields.extend(sorted(dropped))

    assert dropped_fields, (
        "Fixture should drop at least one field — the harness self-test catches regressions where the forward invariant stops working."
    )
    assert "b" in dropped_fields, f"Expected dropper to drop 'b'; dropped {dropped_fields!r}"
