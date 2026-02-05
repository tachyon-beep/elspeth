# Test Audit: test_sink_protocol_compliance.py

**File:** `tests/plugins/sinks/test_sink_protocol_compliance.py`
**Lines:** 61
**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5

## Summary

Parametrized protocol compliance tests for all sink plugins. Uses pytest parametrization to run the same tests against CSVSink, JSONSink, and DatabaseSink.

## Findings

### 1. Defects

**SEVERITY: MEDIUM**
- **Line 61:** Test uses `hasattr(sink, "input_schema")` which is prohibited by CLAUDE.md's prohibition on defensive programming patterns. Should directly access the attribute and let it crash if missing.

### 2. Overmocking

None identified.

### 3. Missing Coverage

**SEVERITY: HIGH**
- **Only tests `name` and `input_schema` attributes.** Missing protocol compliance tests for:
  - `write()` method signature
  - `close()` method
  - `flush()` method
  - `plugin_version` attribute
  - `determinism` attribute
  - `supports_resume` attribute
  - `configure_for_resume()` method
  - `validate_output_target()` method
  - `on_start()` / `on_complete()` lifecycle hooks

**SEVERITY: MEDIUM**
- No test that sinks actually implement `SinkProtocol` (runtime_checkable)
- Missing test for `output_schema` attribute if it exists

### 4. Tests That Do Nothing

**SEVERITY: LOW**
- The test only verifies attributes exist, not that they work correctly. More of a smoke test than compliance test.

### 5. Inefficiency

None - file is appropriately minimal.

### 6. Structural Issues

**SEVERITY: MEDIUM**
- File claims to be `conftest.py` in the first comment but is actually `test_sink_protocol_compliance.py`
- No actual conftest.py exists in the sinks directory - fixtures and parametrization defined here but not reusable by other tests

## Positive Observations

1. Good use of pytest parametrization for cross-sink testing
2. Dynamic import helper is clean and reusable
3. Correct schema types assigned per sink requirements

## Recommendations

1. **Critical:** Replace `hasattr()` with direct attribute access per CLAUDE.md:
   ```python
   def test_has_required_attributes(self, class_path: str, config: dict, expected_name: str):
       sink_class = _import_sink_class(class_path)
       assert sink_class.name == expected_name
       sink = sink_class(config)
       # Access directly - will crash if missing (desired behavior)
       _ = sink.input_schema
   ```
2. Add comprehensive protocol compliance tests for all required methods/attributes
3. Consider using `isinstance(sink, SinkProtocol)` for runtime_checkable protocol verification
4. Rename or restructure - first comment says conftest.py but file is test_sink_protocol_compliance.py
5. Move shared configurations to actual conftest.py
