import pandas as pd

from dmp.plugins.outputs.csv_file import CsvResultSink


def test_csv_result_sink_writes(tmp_path):
    path = tmp_path / "results.csv"
    sink = CsvResultSink(path=path)

    sink.write({
        "results": [
            {
                "row": {"APPID": "1"},
                "response": {"content": "ok"},
                "responses": {"crit": {"content": "crit-ok"}},
            }
        ]
    })

    assert path.exists()
    df = pd.read_csv(path)
    assert "APPID" in df.columns
    assert df.loc[0, "llm_content"] == "ok"
    assert df.loc[0, "llm_crit"] == "crit-ok"


def test_csv_result_sink_overwrite(tmp_path):
    path = tmp_path / "results.csv"
    path.write_text("existing", encoding="utf-8")

    sink = CsvResultSink(path=path, overwrite=False)
    try:
        sink.write({"results": []})
    except FileExistsError:
        pass
    else:
        assert False, "Expected FileExistsError when overwrite disabled"


def test_csv_result_sink_skip_on_error(tmp_path, monkeypatch):
    path = tmp_path / "results.csv"
    sink = CsvResultSink(path=path, on_error="skip")

    def raising_to_csv(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pd.DataFrame, "to_csv", raising_to_csv)

    sink.write({"results": []})
    assert not path.exists()
