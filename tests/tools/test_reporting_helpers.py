from elspeth.tools.reporting import _comparisons_dataframe, _safe_get


def test_safe_get_and_comparisons_dataframe():
    data = {"a": {"b": {"c": 1}}}
    assert _safe_get(data, ("a", "b", "c")) == 1
    assert _safe_get(data, ("a", "x")) is None

    comparative = {
        "variants": {
            "exp1": {"comparisons": {"pluginA": {"m1": 0.1, "m2": -0.2}}},
            "exp2": {"comparisons": {"pluginB": 0.5}},
        }
    }
    df = _comparisons_dataframe(comparative)
    assert set(df.columns) == {"experiment", "plugin", "metric", "delta"}
    assert len(df) == 3

