# Audit: tests/telemetry/exporters/test_console.py

## Summary
**Lines:** 89
**Test Classes:** 2 (Configuration, Registration)
**Quality:** ADEQUATE - Basic coverage but missing export behavior tests

## Findings

### Strengths

1. **Configuration Validation Coverage** (Lines 16-71)
   - Tests default configuration
   - Tests valid format/output values
   - Tests invalid format/output values with error messages
   - Tests type validation with descriptive errors

2. **Plugin Registration Tests** (Lines 74-89)
   - Verifies exporter is in BuiltinExportersPlugin
   - Verifies exporter is in package __all__

### Critical Missing Coverage

1. **No Export Behavior Tests**
   - No tests for `export()` method
   - No tests for actual console output (stdout/stderr)
   - No tests for JSON vs Pretty format output
   - This is the primary functionality of the exporter!

2. **No Lifecycle Tests**
   - No tests for `flush()` behavior
   - No tests for `close()` behavior
   - No tests for idempotent close

3. **No Error Handling Tests**
   - No tests for export failure handling
   - No tests for serialization errors

### Recommendations

This test file needs significant expansion:

```python
def test_export_to_stdout_json_format(capsys):
    """Verify JSON export writes to stdout."""
    exporter = ConsoleExporter()
    exporter.configure({"format": "json", "output": "stdout"})
    event = make_run_started()
    exporter.export(event)
    captured = capsys.readouterr()
    assert "run-123" in captured.out
    # Verify valid JSON
    import json
    json.loads(captured.out.strip())

def test_export_to_stderr(capsys):
    """Verify stderr output."""
    exporter = ConsoleExporter()
    exporter.configure({"output": "stderr"})
    event = make_run_started()
    exporter.export(event)
    captured = capsys.readouterr()
    assert captured.err  # Output went to stderr
    assert not captured.out  # Nothing to stdout
```

## Verdict
**NEEDS IMPROVEMENT** - Configuration tests are good but missing all export behavior tests. The exporter's primary function (writing to console) is untested.
