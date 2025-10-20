import pytest

from elspeth.core.base.types import DataType, DeterminismLevel, PluginType, SecurityLevel
from elspeth.core.security import ensure_determinism_level, ensure_security_level


@pytest.mark.parametrize(
    "text, expected",
    [
        (None, SecurityLevel.UNOFFICIAL),
        ("", SecurityLevel.UNOFFICIAL),
        ("public", SecurityLevel.UNOFFICIAL),
        ("unofficial", SecurityLevel.UNOFFICIAL),
        ("internal", SecurityLevel.OFFICIAL),
        ("official", SecurityLevel.OFFICIAL),
        ("sensitive", SecurityLevel.OFFICIAL_SENSITIVE),
        ("official_sensitive", SecurityLevel.OFFICIAL_SENSITIVE),
        ("OFFICIAL: SENSITIVE", SecurityLevel.OFFICIAL_SENSITIVE),  # Canonical PSPF string
        ("official: sensitive", SecurityLevel.OFFICIAL_SENSITIVE),  # Case-insensitive
        ("OFFICIAL-SENSITIVE", SecurityLevel.OFFICIAL_SENSITIVE),  # Hyphenated variant
        ("official-sensitive", SecurityLevel.OFFICIAL_SENSITIVE),  # Hyphenated, case-insensitive
        ("confidential", SecurityLevel.PROTECTED),
        ("protected", SecurityLevel.PROTECTED),
        ("secret", SecurityLevel.SECRET),
    ],
)
def test_security_level_aliases_and_defaults(text, expected):
    assert ensure_security_level(text) == expected


def test_security_level_comparisons_ordering():
    assert SecurityLevel.UNOFFICIAL < SecurityLevel.OFFICIAL
    assert SecurityLevel.OFFICIAL < SecurityLevel.OFFICIAL_SENSITIVE
    assert SecurityLevel.OFFICIAL_SENSITIVE < SecurityLevel.PROTECTED
    assert SecurityLevel.PROTECTED < SecurityLevel.SECRET
    assert SecurityLevel.SECRET >= SecurityLevel.PROTECTED


def test_security_level_unknown_raises():
    with pytest.raises(ValueError):
        ensure_security_level("topsecret")


@pytest.mark.parametrize(
    "text, expected",
    [
        (None, DeterminismLevel.NONE),
        ("", DeterminismLevel.NONE),
        ("low", DeterminismLevel.LOW),
        ("HIGH", DeterminismLevel.HIGH),
        ("guaranteed", DeterminismLevel.GUARANTEED),
    ],
)
def test_determinism_level_defaults_and_values(text, expected):
    assert ensure_determinism_level(text) == expected


def test_determinism_level_comparisons_ordering():
    assert DeterminismLevel.NONE < DeterminismLevel.LOW
    assert DeterminismLevel.LOW < DeterminismLevel.HIGH
    assert DeterminismLevel.HIGH < DeterminismLevel.GUARANTEED
    assert DeterminismLevel.GUARANTEED >= DeterminismLevel.HIGH


def test_determinism_level_unknown_raises():
    with pytest.raises(ValueError):
        ensure_determinism_level("super")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("str", DataType.STRING),
        ("text", DataType.STRING),
        ("integer", DataType.INT),
        ("double", DataType.FLOAT),
        ("number", DataType.FLOAT),
        ("boolean", DataType.BOOL),
        ("timestamp", DataType.DATETIME),
        ("bytes", DataType.BINARY),
        ("list", DataType.ARRAY),
        ("object", DataType.OBJECT),
        ("int64", DataType.INT64),
        ("category", DataType.CATEGORY),
    ],
)
def test_data_type_from_string_with_aliases(text, expected):
    assert DataType.from_string(text) == expected


@pytest.mark.parametrize(
    "dt, expected",
    [
        (DataType.INT, "int64"),
        (DataType.FLOAT, "float64"),
        (DataType.DATETIME, "datetime64[ns]"),
        (DataType.JSON, "object"),
        (DataType.CATEGORY, "category"),
        (DataType.TIME, "object"),
    ],
)
def test_data_type_to_pandas_dtype(dt, expected):
    assert dt.to_pandas_dtype() == expected


def test_data_type_from_string_errors():
    with pytest.raises(ValueError):
        DataType.from_string(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DataType.from_string("")
    with pytest.raises(ValueError):
        DataType.from_string("nope")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("datasource", PluginType.DATASOURCE),
        ("source", PluginType.DATASOURCE),
        ("output", PluginType.SINK),
        ("row", PluginType.ROW_PLUGIN),
        ("agg", PluginType.AGGREGATOR),
        ("validation", PluginType.VALIDATOR),
        ("early_stopping", PluginType.EARLY_STOP),
        ("baseline-comparison", PluginType.BASELINE),  # hyphen normalized
        ("utility", PluginType.UTILITY),
        ("backplane", PluginType.BACKPLANE),
    ],
)
def test_plugin_type_from_string_aliases(text, expected):
    assert PluginType.from_string(text) == expected


def test_plugin_type_from_string_errors():
    with pytest.raises(ValueError):
        PluginType.from_string(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PluginType.from_string("")
    with pytest.raises(ValueError):
        PluginType.from_string("unknown")
