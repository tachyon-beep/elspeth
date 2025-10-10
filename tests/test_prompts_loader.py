import pytest
from jinja2 import Template

from elspeth.core.prompts.loader import load_template, load_template_pair
from elspeth.core.prompts.template import PromptTemplate


def test_load_template_uses_file_stem_for_name_and_defaults(tmp_path):
    template_path = tmp_path / "greeting.md"
    template_path.write_text("Hello, {{ audience }}!", encoding="utf-8")

    prompt = load_template(template_path, defaults={"audience": "analysts"})

    assert prompt.name == "greeting"
    assert prompt.render() == "Hello, analysts!"


def test_load_template_pair_reuses_engine_and_defaults(tmp_path):
    system_path = tmp_path / "system.md"
    user_path = tmp_path / "user.md"
    system_path.write_text("System", encoding="utf-8")
    user_path.write_text("User {{ field }}", encoding="utf-8")

    class DummyEngine:
        def __init__(self):
            self.calls = []

        def compile(self, source, *, name, defaults=None, metadata=None):
            self.calls.append((source, name, defaults))
            return PromptTemplate(name=name, raw=source, template=Template(source), defaults=defaults or {})

    engine = DummyEngine()
    defaults = {"field": "value"}

    system_template, user_template = load_template_pair(
        system_path,
        user_path,
        engine=engine,
        defaults=defaults,
    )

    assert len(engine.calls) == 2
    assert system_template.name == "system_prompt"
    assert user_template.render() == "User value"


def test_load_template_missing_file_raises(tmp_path):
    missing_path = tmp_path / "missing.md"
    with pytest.raises(FileNotFoundError):
        load_template(missing_path)
