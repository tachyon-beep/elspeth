## tests/engine/test_orchestrator_audit.py
**Lines:** 1424
**Tests:** 12
**Audit:** WARN

### Summary
This file tests audit trail functionality in the Orchestrator, including landscape entries, config recording, export features, and node metadata. Tests are well-organized into clear test classes with good docstrings explaining the purpose. However, two tests violate test path integrity by using manual graph construction with `ExecutionGraph()` and direct attribute assignment (`graph._transform_id_map`, etc.) instead of the production `ExecutionGraph.from_plugin_instances()` factory.

### Findings

#### Critical
- **Test Path Integrity Violation - `test_node_metadata_records_plugin_version` (lines 920-929)**: Uses manual graph construction with `ExecutionGraph()`, `graph.add_node()`, `graph.add_edge()`, and direct assignment of private attributes (`graph._transform_id_map`, `graph._sink_id_map`, `graph._default_sink`). This bypasses the production code path and could hide bugs in `from_plugin_instances()`. Per CLAUDE.md "Test Path Integrity" section, this pattern allowed BUG-LINEAGE-01 to hide for weeks.

- **Test Path Integrity Violation - `test_node_metadata_records_determinism` (lines 1034-1044)**: Same manual graph construction pattern. While the test verifies determinism is recorded correctly, it doesn't exercise the production path that would actually construct graphs in real usage.

#### Warning
- **Heavy Boilerplate / Copy-Paste Pattern**: Each test defines its own `ListSource`, `CollectSink`, and sometimes `IdentityTransform` classes inline. Lines 46-91, 186-229, 324-362, 456-489, 568-605, 681-726, 773-806, 858-907, 973-1022, 1086-1143, 1224-1263 contain near-identical implementations. These could be extracted to fixtures or the helper module to reduce duplication and test maintenance burden.

- **Unused `plugin_manager` Fixture**: `test_orchestrator_exports_landscape_when_configured`, `test_orchestrator_export_with_signing`, `test_orchestrator_export_requires_signing_key_when_sign_enabled`, `test_orchestrator_no_export_when_disabled` all accept `plugin_manager` fixture but never use it. This clutters the test signature and may indicate incomplete test setup.

- **Inconsistent Graph Construction**: Some tests use `build_production_graph(config)` (lines 104, 747, 821) which is correct, while `test_node_metadata_records_plugin_version` and `test_node_metadata_records_determinism` use manual construction. This inconsistency is confusing and suggests these two tests were written before the helper was available or weren't updated.

#### Info
- **Good Practice - Production Path Usage**: `test_run_records_landscape_entries`, `test_run_records_resolved_config`, `test_run_with_empty_config_records_empty` correctly use `build_production_graph(config)` helper.

- **Good Practice - Settings-Based Tests**: `test_orchestrator_exports_landscape_when_configured`, `test_orchestrator_export_with_signing`, `test_orchestrator_no_export_when_disabled`, `test_aggregation_node_uses_transform_metadata`, `test_config_gate_node_uses_engine_version`, `test_coalesce_node_uses_engine_version` use `ExecutionGraph.from_plugin_instances()` directly with real settings, which is the correct production path.

- **Well-Documented Bug Fixes**: Tests document which bugs they verify (P2-2026-01-21, P2-2026-01-15-node-metadata-hardcoded) with clear docstrings explaining the historical context.

- **Proper Assertions**: Tests verify meaningful properties (hash integrity, metadata recording, export signatures) rather than just checking completion status.

### Verdict
**WARN** - Two tests violate test path integrity with manual graph construction. These should be migrated to use `build_production_graph()` or `ExecutionGraph.from_plugin_instances()`. Additionally, significant boilerplate duplication could be extracted to fixtures. The unused `plugin_manager` fixtures should be removed if not needed.
