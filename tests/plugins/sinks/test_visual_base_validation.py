import pytest

from elspeth.plugins.nodes.sinks._visual_base import BaseVisualSink


class _Dummy(BaseVisualSink):
    def write(self, results, *, metadata=None):  # noqa: D401, ARG002
        return None

    def produces(self):  # pragma: no cover
        return []

    def consumes(self):  # pragma: no cover
        return []

    def collect_artifacts(self):  # pragma: no cover
        return {}


def test_visual_base_validation_errors():
    with pytest.raises(ValueError):
        _Dummy(base_path=".", file_stem="x", dpi=0, allow_downgrade=True)
    with pytest.raises(ValueError):
        _Dummy(base_path=".", file_stem="x", figure_size=(0, 2), allow_downgrade=True)
    with pytest.raises(ValueError):
        _Dummy(base_path=".", file_stem="x", on_error="halt", allow_downgrade=True)


def test_visual_base_validate_formats_normalizes():
    d = _Dummy(base_path=".", file_stem="x", formats=["PNG", "bad", "html"], allow_downgrade=True)
    assert d.formats == ["png", "html"]
