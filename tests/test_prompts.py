import pytest

from dmp.core.prompts import PromptEngine, PromptRenderingError


def test_auto_convert_format_placeholders():
    engine = PromptEngine()
    template = engine.compile("Hello {name}", name="greeting")
    result = engine.render(template, {"name": "World"})
    assert result == "Hello World"


def test_template_conditionals():
    engine = PromptEngine()
    tpl = engine.compile("{{ 'Hi ' + user if user else 'Hi there' }}", name="cond")
    assert engine.render(tpl, {"user": "Sam"}).strip() == "Hi Sam"
    assert engine.render(tpl, {"user": ""}).strip() == "Hi there"


def test_missing_variable_raises():
    engine = PromptEngine()
    tpl = engine.compile("Hello {{ name }}", name="missing")
    with pytest.raises(PromptRenderingError):
        engine.render(tpl, {})


def test_clone_template():
    engine = PromptEngine()
    tpl = engine.compile("Value {{ item }}", name="base")
    clone = tpl.clone(name="clone")
    assert engine.render(clone, {"item": 5}).strip() == "Value 5"


def test_default_filter():
    engine = PromptEngine()
    tpl = engine.compile("{{ value|default('fallback') }}", name="default")
    assert engine.render(tpl, {}) == "fallback"
    assert engine.render(tpl, {"value": "set"}) == "set"
