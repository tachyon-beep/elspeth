import elspeth.core.validation as validation
from elspeth.core.validation import ValidationReport, validate_schema


def test_validate_schema_anyof_failure_reports_context():
    schema = {
        "type": "object",
        "anyOf": [
            {"required": ["name"]},
            {"required": ["plugin"]},
        ],
    }

    messages = list(validate_schema({}, schema, context="middleware"))

    assert messages
    assert any("did not match any allowed schemas" in message.message for message in messages)
    assert all(message.context == "middleware" for message in messages)


def test_validate_plugin_reference_type_checks():
    report = ValidationReport()

    def validator(plugin, options):
        if plugin != "known":
            raise ValueError("unknown plugin")

    validation._validate_plugin_reference(report, entry="not-a-mapping", kind="sink", validator=validator)
    validation._validate_plugin_reference(report, entry={"options": {}}, kind="sink", validator=validator)
    validation._validate_plugin_reference(report, entry={"plugin": 123}, kind="sink", validator=validator)
    validation._validate_plugin_reference(report, entry={"plugin": "unknown"}, kind="sink", validator=validator)

    messages = [msg.format() for msg in report.errors]
    assert "sink configuration must be a mapping" in messages[0]
    assert any("Missing 'plugin'" in message for message in messages)
    assert any("Plugin name must be a string" in message for message in messages)
    assert any("unknown plugin" in message for message in messages)


def test_validate_plugin_list_requires_sequence():
    report = ValidationReport()

    validation._validate_plugin_list(report, entries="not-a-list", validator=lambda *_: None, context="validation")

    assert any("Expected a list of plugin definitions" in msg.format() for msg in report.errors)


def test_validate_plugin_reference_requires_security_level():
    report = ValidationReport()

    validation._validate_plugin_reference(
        report,
        entry={"plugin": "known", "options": {}},
        kind="sink",
        validator=lambda *_: None,
        require_security_level=True,
    )

    messages = [msg.format() for msg in report.errors]
    assert any("security_level" in message for message in messages)
