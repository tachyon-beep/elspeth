# Test Audit: tests/plugins/azure/test_blob_sink_resume.py

**Lines:** 32
**Test count:** 2
**Audit status:** PASS

## Summary

This is a minimal but focused test file that verifies `AzureBlobSink` correctly declares it does not support resume functionality. The tests verify both the class attribute (`supports_resume=False`) and that the `configure_for_resume()` method raises `NotImplementedError` with an appropriate message. This is important for ensuring the plugin correctly communicates its capabilities.

## Findings

### 🔵 Info

1. **Lines 6-10 - Class attribute test**: Testing `supports_resume` at the class level (not instance level) is correct since this is a protocol attribute that should be consistent across all instances.

2. **Lines 13-32 - Error message validation**: The test verifies not just that `NotImplementedError` is raised, but that the error message contains relevant context ("AzureBlobSink" and either "immutable" or "append"). This is good practice for ensuring helpful error messages.

3. **Lines 19-25 - Minimal config for test**: The test creates a sink with just enough config to pass validation. This is appropriate since the test is about the resume capability, not about configuration.

## Verdict

**KEEP** - While small, this test file serves an important purpose: ensuring that plugins correctly declare their capabilities. The resume capability is a critical feature for crash recovery, and having explicit tests that certain plugins don't support it prevents runtime surprises. No issues found.
