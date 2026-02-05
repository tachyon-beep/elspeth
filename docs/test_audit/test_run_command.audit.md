# Test Audit: tests/cli/test_run_command.py

**Lines:** 842
**Test count:** 22
**Audit status:** PASS

## Summary

This is a comprehensive test file for the `elspeth run` CLI command. It covers happy paths, error cases, resource cleanup, progress output, graph construction, payload storage, and directory auto-creation. The tests use real CLI invocation via `CliRunner` and verify actual file system artifacts and database state, making them meaningful integration tests rather than mock-heavy unit tests.

## Findings

### 🔵 Info (minor suggestions or observations)
- **Line 75:** The assertion `"completed" in result.output.lower() or "rows" in result.output.lower()` is somewhat loose but acceptable since it's testing that some summary output appears, not the exact format.

- **Line 92:** The assertion `"dry" in result.output.lower() or "would" in result.output.lower()` uses an OR condition, making it tolerant of different message formats. This is pragmatic for CLI output testing.

- **Lines 294-411:** The resource cleanup tests (`test_run_closes_database_after_success` and `test_run_closes_database_after_failure`) use mock patching appropriately to verify that `close()` is called, which is a legitimate use case for mocking - verifying side effects on resource cleanup.

- **Lines 482-548:** The `test_run_constructs_graph_once` test is a well-designed regression test that patches `from_plugin_instances` to count invocations. This catches the bug where validation and execution used different graph instances.

- **Lines 550-630:** The `test_validated_graph_has_consistent_node_ids` test goes further by verifying that node IDs in the database match what a rebuilt graph would produce, ensuring deterministic graph construction.

## Verdict
**KEEP** - This is an exemplary test file. It tests real behavior through the CLI interface, verifies actual artifacts (files, database records), and includes targeted regression tests for specific bugs. The mock usage is appropriate (tracking calls, not replacing behavior).
