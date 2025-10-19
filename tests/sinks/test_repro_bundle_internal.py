from __future__ import annotations

import pandas as pd

from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink


def test_get_retained_path_from_dataframe(tmp_path):
    df = pd.DataFrame({"a": [1, 2]})
    df.attrs["retained_local_path"] = str(tmp_path / "source.csv")

    sink = ReproducibilityBundleSink(base_path=str(tmp_path))
    assert sink._get_retained_path(df) == str(tmp_path / "source.csv")


def test_get_retained_path_non_string_ignored(tmp_path):
    df = pd.DataFrame({"a": [1]})
    df.attrs["retained_local_path"] = 123  # not a string

    sink = ReproducibilityBundleSink(base_path=str(tmp_path))
    assert sink._get_retained_path(df) is None

