import pandas as pd
import pytest

from elspeth.core.base.schema.inference import infer_schema_from_dataframe


def test_infer_schema_basic_types_and_required_optional():
    df = pd.DataFrame(
        {
            "i": pd.Series([1, 2], dtype="int64"),
            "f": pd.Series([1.2, 3.4], dtype="float64"),
            "b": pd.Series([True, False], dtype="bool"),
            "s": pd.Series(["a", "b"], dtype="object"),
            "t": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        }
    )

    # Only some columns required; others optional
    Schema = infer_schema_from_dataframe(df, required_columns=["i", "s"])  # noqa: N806

    # Required fields must be present
    ok = Schema(i=1, s="x")
    assert ok.i == 1 and ok.s == "x"

    # Optional fields accept None
    ok2 = Schema(i=2, s="y", f=None, b=None, t=None)
    assert ok2.f is None and ok2.b is None and ok2.t is None


def test_infer_schema_unknown_dtype_defaults_to_str():
    df = pd.DataFrame({"c": pd.Series(["x", "y"], dtype="category")})
    Schema = infer_schema_from_dataframe(df)  # noqa: N806
    # Should accept strings for category column (mapped to str)
    row = Schema(c="value")
    assert row.c == "value"

