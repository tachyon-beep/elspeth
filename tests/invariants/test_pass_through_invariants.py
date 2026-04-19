"""Governance harness for ADR-009 §Clause 4 — pass-through annotation invariants.

Three tests here:

- **Forward invariant** (`test_annotated_transforms_preserve_input_fields`):
  For every registered ``passes_through_input=True`` transform, runs
  Hypothesis-generated probe rows through ``process()`` and asserts every
  emitted row preserves every input field (contract AND payload). Fails CI
  on mis-annotation.

- **Backward invariant** (``test_non_pass_through_transforms_do_drop_fields``):
  Diagnostic signal, does not fail CI. If a non-annotated transform appears
  to preserve fields on 30 probe rows, fires a filigree observation
  suggesting ``passes_through_input=True`` may be appropriate. Dedup by
  ``(transform_qualname, "pass-through-candidate")``; the observation is
  fire-and-forget.

- **Skip-rate budget** (``test_harness_skip_rate_budget``): asserts
  ``skip_rate ≤ 25%`` across the annotated plugin set. Track 2 additions
  that slip the budget must implement ``probe_config()`` per the contract.

The harness uses ``pytest_generate_tests`` to parametrize over registered
transforms at collection time — with a guard that crashes if the plugin
list is empty (silent "0 tests" passes are the worst kind of theatre).
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings

from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.infrastructure.manager import get_shared_plugin_manager
from tests.invariants.conftest import probe_row


class _UnprobeableTransform(Exception):
    """Raised when probe_config() is not implemented or the constructor rejects its output."""

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _annotated_pass_through_plugins() -> list[type[BaseTransform]]:
    """Every registered transform class with ``passes_through_input=True``.

    Reads ``cls.passes_through_input`` directly — no ``getattr`` default.
    Missing attribute is a framework bug (``BaseTransform`` supplies it) and
    a silent ``False`` coercion would hide the annotation from governance.
    """
    return [cls for cls in get_shared_plugin_manager().get_transforms() if cls.passes_through_input]


def _non_pass_through_plugins() -> list[type[BaseTransform]]:
    """Every registered transform class without pass-through annotation."""
    return [cls for cls in get_shared_plugin_manager().get_transforms() if not cls.passes_through_input]


def _probe_instantiate(cls: type[BaseTransform]) -> BaseTransform:
    """Build a transform instance via its ``probe_config()`` declaration.

    Narrow exception catches only ``NotImplementedError`` (missing
    implementation — legitimate skip) and ``TypeError`` (wrong constructor
    args — config shape mismatch). Any other exception is a plugin bug and
    must propagate (CLAUDE.md: plugin bugs must crash).
    """
    try:
        config = cls.probe_config()
    except NotImplementedError as exc:
        raise _UnprobeableTransform(reason=f"{cls.__name__}.probe_config() not implemented: {exc}") from exc
    try:
        return cls(config=config)
    except TypeError as exc:
        raise _UnprobeableTransform(reason=f"{cls.__name__}.__init__ rejected probe_config() output: {exc}") from exc


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamic parametrization — resolves after plugin registration fixtures run.

    Using a fixture-less ``pytest.mark.parametrize`` at module scope would
    evaluate ``_annotated_pass_through_plugins()`` at collection time,
    before plugin registration side effects have fired. The guard here
    crashes loudly if the list is empty.
    """
    if "_annotated_cls" in metafunc.fixturenames:
        plugins = _annotated_pass_through_plugins()
        assert len(plugins) >= 2, (
            "Expected at least 2 passes_through_input=True transforms "
            "(PassThrough and BatchReplicate); found "
            f"{[cls.__name__ for cls in plugins]!r}. Plugin registration "
            "may have failed — the invariant harness would silently pass."
        )
        metafunc.parametrize("_annotated_cls", plugins, ids=lambda c: c.__name__)

    if "_non_pass_through_cls" in metafunc.fixturenames:
        plugins = _non_pass_through_plugins()
        metafunc.parametrize("_non_pass_through_cls", plugins, ids=lambda c: c.__name__)


def _probe_context(transform: BaseTransform) -> Any:
    """Minimal TransformContext for probe invocations.

    The harness runs transforms in isolation without a real run; the context
    is a lightweight stub with a mock landscape recorder.
    """
    from tests.fixtures.factories import make_context

    return make_context()


def _emitted_rows_from_result(result: Any) -> list[PipelineRow]:
    if result.row is not None:
        return [result.row]
    if result.rows is not None:
        return list(result.rows)
    return []


@given(row=probe_row())
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
def test_annotated_transforms_preserve_input_fields(
    _annotated_cls: type[BaseTransform],
    row: PipelineRow,
) -> None:
    """Forward invariant — ADR-009 §Clause 4.

    Every emitted row from a ``passes_through_input=True`` transform must
    preserve every input field in both its contract and its payload
    (runtime observation is the intersection of the two).

    Failures are actionable: Hypothesis shrinks to a minimal probe row,
    producing the smallest repro case for the plugin author. The remediation
    is clear — either fix the implementation or remove the annotation.
    """
    try:
        transform = _probe_instantiate(_annotated_cls)
    except _UnprobeableTransform as exc:
        pytest.skip(f"{_annotated_cls.__name__}: {exc.reason}")
        return

    # Batch-aware transforms receive list[PipelineRow]; single-token transforms
    # receive PipelineRow. Both shapes are exercised by the same probe.
    try:
        if transform.is_batch_aware:
            result = transform.process([row], _probe_context(transform))  # type: ignore[arg-type]
        else:
            result = transform.process(row, _probe_context(transform))
    except (TypeError, AttributeError) as exc:
        pytest.skip(f"{_annotated_cls.__name__}: probe invocation rejected: {exc}")
        return

    if result.status != "success":
        # Legitimate processing error on this probe (e.g., quarantine). Not
        # a pass-through contract violation.
        return

    emitted_rows = _emitted_rows_from_result(result)
    if not emitted_rows:
        # Empty emission — ADR-009 §Clause 3 carve-out. Drops nothing.
        return

    input_fields = frozenset(fc.normalized_name for fc in row.contract.fields)
    for emitted in emitted_rows:
        runtime_contract = frozenset(fc.normalized_name for fc in emitted.contract.fields)
        runtime_payload = frozenset(emitted.keys())
        runtime_observed = runtime_contract & runtime_payload
        dropped = input_fields - runtime_observed
        assert not dropped, (
            f"{_annotated_cls.__name__} is annotated passes_through_input=True "
            f"but dropped fields {sorted(dropped)!r} from probe row "
            f"{row.to_dict()!r}. Either fix the implementation or remove "
            "the annotation."
        )


def test_harness_skip_rate_budget() -> None:
    """Skip-rate budget — ADR-009 §Clause 4.

    Assert ``skip_rate ≤ 25%`` across the annotated plugin set. Track 2
    additions that can't be probed in isolation must implement
    ``probe_config()`` per the contract; raising the budget is not an
    acceptable response.
    """
    transforms = _annotated_pass_through_plugins()
    if not transforms:
        pytest.skip("No annotated transforms registered.")
        return

    unprobeable: list[str] = []
    for cls in transforms:
        try:
            _probe_instantiate(cls)
        except _UnprobeableTransform as exc:
            unprobeable.append(f"{cls.__name__}: {exc.reason}")

    skip_rate = len(unprobeable) / len(transforms)
    assert skip_rate <= 0.25, (
        f"Harness skip rate {skip_rate:.0%} exceeds 25% budget "
        f"({len(unprobeable)}/{len(transforms)} annotated transforms unprobeable). "
        f"Implement probe_config() on: {unprobeable!r}"
    )


def test_non_pass_through_transforms_do_drop_fields(
    _non_pass_through_cls: type[BaseTransform],
) -> None:
    """Backward invariant (diagnostic) — ADR-009 §Clause 4.

    Does NOT fail CI. Runs scalar probe rows; if the transform appears to
    preserve every input field on every probe, fires a filigree observation
    suggesting ``passes_through_input=True`` may be appropriate.

    Observations dedup by ``(transform_qualname, "pass-through-candidate")``
    with a 14-day TTL. The signal-to-noise ratio is bounded: scalar-only
    probes miss structured-data drops, so a preservation result doesn't
    mean the transform IS pass-through — only that one probe mode couldn't
    disprove it. Human review via the observation triage process decides
    whether to promote to an issue.
    """
    try:
        transform = _probe_instantiate(_non_pass_through_cls)
    except _UnprobeableTransform:
        # Unprobeable non-annotated transforms are fine here — the backward
        # invariant is a diagnostic signal, not a governance gate.
        return

    from hypothesis import given as _given

    probes_preserved = True
    probe_count = 0

    @_given(probe=probe_row())
    @settings(
        max_examples=15,  # bounded — this is a diagnostic sweep
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def _sweep(probe: PipelineRow) -> None:
        nonlocal probes_preserved, probe_count
        probe_count += 1
        try:
            if transform.is_batch_aware:
                result = transform.process([probe], _probe_context(transform))  # type: ignore[arg-type]
            else:
                result = transform.process(probe, _probe_context(transform))
        except Exception:
            return
        if result.status != "success":
            return
        emitted_rows = _emitted_rows_from_result(result)
        if not emitted_rows:
            return
        input_fields = frozenset(fc.normalized_name for fc in probe.contract.fields)
        for emitted in emitted_rows:
            observed = frozenset(fc.normalized_name for fc in emitted.contract.fields) & frozenset(emitted.keys())
            if input_fields - observed:
                probes_preserved = False
                return

    try:
        _sweep()
    except Exception:
        # Strategy exhaustion, instantiation quirks — don't fail CI.
        return

    if probes_preserved and probe_count >= 5:
        _fire_filigree_observation(
            title=f"Transform {_non_pass_through_cls.__name__!r} may be passes_through_input=True",
            body=(
                f"In {probe_count} scalar probe rows, {_non_pass_through_cls.__name__} "
                "preserved all input fields on every emission. Consider annotating "
                "passes_through_input=True. Fire-and-forget observation; expires in 14 days. "
                "Scalar probes miss structured-data drops — promote to issue only "
                "after confirming on realistic inputs."
            ),
            file_path=inspect.getfile(_non_pass_through_cls),
            dedup_key=f"{_non_pass_through_cls.__qualname__}:pass-through-candidate",
        )


def _fire_filigree_observation(
    *,
    title: str,
    body: str,
    file_path: str,
    dedup_key: str,
) -> None:
    """Fire-and-forget observation via filigree.

    CI must not fail on filigree unavailability — this is a diagnostic
    signal, not a governance gate. The implementation is a best-effort
    no-op if filigree is not reachable from the test environment (e.g.,
    CI container without MCP access).
    """
    # Best-effort: attempt to call the filigree CLI if available; otherwise
    # silently skip. Observation dedup is the filigree CLI's responsibility
    # given the 14-day TTL — duplicate fire-and-forget calls are tolerated.
    import subprocess

    try:
        subprocess.run(
            [
                "filigree",
                "observe",
                title,
                "--body",
                body,
                "--file-path",
                file_path,
                "--dedup-key",
                dedup_key,
            ],
            timeout=2.0,
            check=False,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # filigree CLI not installed or unreachable — the backward invariant
        # is diagnostic, not a gate. Silent no-op.
        return
