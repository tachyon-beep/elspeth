import pandas as pd

from elspeth.core.pipeline.processing import prepare_prompt_context


def test_prepare_prompt_context_filters_and_aliases():
    row = pd.Series({"APPID": "1", "name": "Alice", "extra": "ignored"})

    context = prepare_prompt_context(
        row,
        include_fields=["APPID", "name"],
        alias_map={"name": "applicant"},
    )

    assert context == {"APPID": "1", "applicant": "Alice"}
