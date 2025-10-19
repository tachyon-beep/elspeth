import re

import pandas as pd
import pytest
from pydantic import ValidationError

from elspeth.core.base.schema.model_factory import schema_from_config, _parse_type_string


@pytest.mark.parametrize(
    "text, expected",
    [
        ("str", str),
        ("string", str),
        ("int", int),
        ("integer", int),
        ("float", float),
        ("number", float),
        ("bool", bool),
        ("boolean", bool),
        ("datetime", pd.Timestamp),
        ("timestamp", pd.Timestamp),
    ],
)
def test_parse_type_string_supported(text, expected):
    assert _parse_type_string(text) is expected


def test_parse_type_string_unsupported():
    with pytest.raises(ValueError):
        _parse_type_string("blob")


def test_schema_from_config_required_optional_and_constraints():
    cfg = {
        "name": "string",
        "age": {"type": "integer", "min": 0, "max": 120},
        "nickname": {"type": "string", "required": False, "min_length": 2, "max_length": 10, "pattern": r"^[A-Za-z]+$"},
        "ts": {"type": "timestamp"},
    }
    Schema = schema_from_config(cfg)  # noqa: N806

    ok = Schema(name="Alice", age=30, nickname=None, ts=pd.Timestamp("2024-03-01"))
    assert ok.age == 30 and ok.nickname is None

    # Violations: bounds and string length/pattern
    with pytest.raises(ValidationError):
        Schema(name="A", age=-1, ts=pd.Timestamp("2024-03-01"))

    with pytest.raises(ValidationError):
        Schema(name="Bob", age=200, nickname="a", ts=pd.Timestamp("2024-03-01"))

    with pytest.raises(ValidationError):
        Schema(name="Bob", age=20, nickname="toolongnickname", ts=pd.Timestamp("2024-03-01"))

    with pytest.raises(ValidationError):
        Schema(name="Bob", age=20, nickname="nick_1", ts=pd.Timestamp("2024-03-01"))


def test_schema_from_config_rejects_regex_key():
    cfg = {
        "nickname": {"type": "string", "regex": r"^[A-Za-z]+$"},
    }
    with pytest.raises(ValueError):
        schema_from_config(cfg)
