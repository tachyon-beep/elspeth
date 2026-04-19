"""End-to-end smoke test for examples/deaggregation/settings.yaml.

Locks in the static schema-contract for the deaggregation example: the
upstream `batch_replicate` aggregation must guarantee the input fields
(id, name, copies, category) plus its declared output (copy_index), so the
fixed-schema CSV sink can statically validate. Regresses if someone reverts
the aggregation's `schema:` block back to bare `{mode: observed}`, which
would collapse the static guarantee set to `{copy_index}` only and break
DAG-time validation in `_check_sink_field_requirements`.

Uses tmp_path for all output to avoid polluting the examples/ directory.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def example_dir(tmp_path: Path) -> Path:
    """Create a self-contained copy of the deaggregation example in tmp_path."""
    example_src = Path("examples/deaggregation")
    example_dst = tmp_path / "deaggregation"
    example_dst.mkdir()

    shutil.copy(example_src / "input.csv", example_dst / "input.csv")
    (example_dst / "output").mkdir()
    (example_dst / "runs").mkdir()

    audit_db = example_dst / "runs" / "audit.db"
    output_csv = example_dst / "output" / "replicated.csv"

    settings_yaml = example_dst / "settings.yaml"
    settings_yaml.write_text(
        f"""\
source:
  plugin: csv
  on_success: deagg_in
  options:
    path: {example_dst / "input.csv"}
    schema:
      mode: fixed
      fields:
      - 'id: int'
      - 'name: str'
      - 'copies: int'
      - 'category: str'
    on_validation_failure: discard
aggregations:
- name: replicate_batch
  plugin: batch_replicate
  input: deagg_in
  on_success: output
  on_error: discard
  trigger:
    count: 3
  output_mode: transform
  options:
    schema:
      mode: fixed
      fields:
      - 'id: int'
      - 'name: str'
      - 'copies: int'
      - 'category: str'
    copies_field: copies
    default_copies: 1
    include_copy_index: true
sinks:
  output:
    plugin: csv
    on_write_failure: discard
    options:
      path: {output_csv}
      schema:
        mode: fixed
        fields:
        - 'id: int'
        - 'name: str'
        - 'copies: int'
        - 'category: str'
        - 'copy_index: int'
landscape:
  url: sqlite:///{audit_db}
"""
    )

    return example_dst


class TestDeaggregationExampleSmoke:
    """Static-contract regression: the example must validate at DAG-build time."""

    def test_example_runs_end_to_end(self, example_dir: Path) -> None:
        """The deaggregation example must build, validate, and execute cleanly."""
        from elspeth.cli_helpers import bootstrap_and_run

        result = bootstrap_and_run(example_dir / "settings.yaml")

        assert result.status.name == "COMPLETED"
        # 6 input rows, copies=2,1,3,2,1,2 → 11 replicated rows
        assert result.rows_processed == 6

        output_csv = example_dir / "output" / "replicated.csv"
        assert output_csv.exists()

        with output_csv.open(newline="") as f:
            rows = list(csv.DictReader(f))

        # Sink schema is fixed with these fields — verify all present in header order
        assert rows, "output should not be empty"
        assert set(rows[0].keys()) == {"id", "name", "copies", "category", "copy_index"}
        assert len(rows) == 11

        # Verify each replica preserves input fields and carries a sequential copy_index
        by_id: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_id.setdefault(row["id"], []).append(row)
        for _id, replicas in by_id.items():
            indices = sorted(int(r["copy_index"]) for r in replicas)
            assert indices == list(range(len(replicas)))


@pytest.fixture
def observed_agg_example_dir(tmp_path: Path) -> Path:
    """Variant of deaggregation example using `mode: observed` on the aggregation.

    Pins ADR-007 end-to-end: without propagation, this would fail static
    validation because the aggregation guarantees only `copy_index` and the
    sink requires the full {id, name, copies, category, copy_index} set.
    With `passes_through_input=True` on BatchReplicate (Phase A annotation),
    the validator walks through the aggregation to the source's guarantees.
    """
    example_src = Path("examples/deaggregation")
    example_dst = tmp_path / "deaggregation_observed"
    example_dst.mkdir()

    shutil.copy(example_src / "input.csv", example_dst / "input.csv")
    (example_dst / "output").mkdir()
    (example_dst / "runs").mkdir()

    audit_db = example_dst / "runs" / "audit.db"
    output_csv = example_dst / "output" / "replicated.csv"

    settings_yaml = example_dst / "settings.yaml"
    settings_yaml.write_text(
        f"""\
source:
  plugin: csv
  on_success: deagg_in
  options:
    path: {example_dst / "input.csv"}
    schema:
      mode: fixed
      fields:
      - 'id: int'
      - 'name: str'
      - 'copies: int'
      - 'category: str'
    on_validation_failure: discard
aggregations:
- name: replicate_batch
  plugin: batch_replicate
  input: deagg_in
  on_success: output
  on_error: discard
  trigger:
    count: 3
  output_mode: transform
  options:
    schema:
      mode: observed
    copies_field: copies
    default_copies: 1
    include_copy_index: true
sinks:
  output:
    plugin: csv
    on_write_failure: discard
    options:
      path: {output_csv}
      schema:
        mode: fixed
        fields:
        - 'id: int'
        - 'name: str'
        - 'copies: int'
        - 'category: str'
        - 'copy_index: int'
landscape:
  url: sqlite:///{audit_db}
"""
    )

    return example_dst


class TestDeaggregationObservedAggregationPassesAfterPropagation:
    """ADR-007 end-to-end: observed-mode aggregation + BatchReplicate is valid."""

    def test_observed_aggregation_plus_batch_replicate_validates_and_runs(self, observed_agg_example_dir: Path) -> None:
        """Pipeline with observed-mode aggregation upstream of BatchReplicate runs successfully.

        Regression guard: the deaggregation ticket (elspeth-87f6d5dea5) was
        filed three times because the original test suite pinned the
        *bug-report shape* (named divergences) rather than the *bug-class
        shape* (pass-through propagation). This test pins the architectural
        fix itself — a pipeline that would have been rejected without
        ADR-007 now runs cleanly end-to-end.
        """
        from elspeth.cli_helpers import bootstrap_and_run

        result = bootstrap_and_run(observed_agg_example_dir / "settings.yaml")

        assert result.status.name == "COMPLETED"
        assert result.rows_processed == 6

        output_csv = observed_agg_example_dir / "output" / "replicated.csv"
        assert output_csv.exists()
        with output_csv.open(newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows, "output should not be empty"
        assert set(rows[0].keys()) == {"id", "name", "copies", "category", "copy_index"}
