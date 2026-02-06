# Test Suite Audit Manifest

**Generated:** 2026-02-05
**Total Files:** 434
**Total Lines:** 209,464
**Average Lines per File:** 483

## Large Files (>2000 lines - require individual batches)

| File | Lines |
|------|-------|
| tests/core/test_dag.py | 3508 |
| tests/engine/test_integration.py | 3696 |
| tests/engine/test_aggregation_integration.py | 3228 |
| tests/core/test_config.py | 3106 |
| tests/core/retention/test_purge.py | 2425 |

## Batches

### Batch 1 (1 file, 461 lines)
- tests/audit/test_plugin_schema_contracts.py (461)

### Batch 2 (2 files, 1280 lines)
- tests/cli/test_cli.py (1039)
- tests/cli/test_cli_helpers.py (241)

### Batch 3 (4 files, 1411 lines)
- tests/cli/test_cli_helpers_db.py (223)
- tests/cli/test_error_boundaries.py (490)
- tests/cli/test_execution_result.py (119)
- tests/cli/test_explain_command.py (294)
- tests/cli/test_explain_tui.py (685 - SKIP, would exceed 2000)

### Batch 4 (2 files, 1164 lines)
- tests/cli/test_explain_tui.py (685)
- tests/cli/test_plugin_errors.py (479)

### Batch 5 (4 files, 1541 lines)
- tests/cli/test_plugins_command.py (219)
- tests/cli/test_run_command.py (842)
- tests/cli/test_run_with_row_plugins.py (244)
- tests/cli/test_secrets_loading.py (214)

### Batch 6 (1 file, 236 lines)
- tests/cli/test_validate_command.py (236)

### Batch 7 (5 files, 869 lines)
- tests/contracts/config/test_runtime_checkpoint.py (203)
- tests/contracts/config/test_runtime_common.py (188)
- tests/contracts/config/test_runtime_concurrency.py (107)
- tests/contracts/config/test_runtime_rate_limit.py (106)
- tests/contracts/config/test_runtime_retry.py (265)

### Batch 8 (4 files, 1163 lines)
- tests/contracts/sink_contracts/test_csv_sink_contract.py (379)
- tests/contracts/sink_contracts/test_sink_protocol.py (336)
- tests/contracts/source_contracts/test_csv_source_contract.py (264)
- tests/contracts/source_contracts/test_source_protocol.py (184)

### Batch 9 (1 file, 1972 lines)
- tests/contracts/test_audit.py (1972)

### Batch 10 (5 files, 1296 lines)
- tests/contracts/test_config.py (135)
- tests/contracts/test_contract_builder.py (328)
- tests/contracts/test_contract_narrowing.py (222)
- tests/contracts/test_contract_propagation.py (656 - SKIP)

### Batch 11 (2 files, 1117 lines)
- tests/contracts/test_contract_propagation.py (656)
- tests/contracts/test_contract_records.py (461)

### Batch 12 (5 files, 1478 lines)
- tests/contracts/test_contract_violation_error.py (325)
- tests/contracts/test_contract_violations.py (243)
- tests/contracts/test_data.py (57)
- tests/contracts/test_enums.py (166)
- tests/contracts/test_errors.py (645)

### Batch 13 (5 files, 931 lines)
- tests/contracts/test_events.py (125)
- tests/contracts/test_field_contract.py (444)
- tests/contracts/test_gate_result_contract.py (78)
- tests/contracts/test_header_modes.py (167)
- tests/contracts/test_identity.py (130) - SKIP

### Batch 14 (5 files, 930 lines)
- tests/contracts/test_identity.py (130)
- tests/contracts/test_leaf_boundary.py (126)
- tests/contracts/test_pipeline_row.py (414)
- tests/contracts/test_plugin_protocols.py (27)
- tests/contracts/test_plugin_schema.py (66)
- tests/contracts/test_results.py (736 - SKIP)

### Batch 15 (2 files, 1059 lines)
- tests/contracts/test_results.py (736)
- tests/contracts/test_routing.py (323)

### Batch 16 (2 files, 1540 lines)
- tests/contracts/test_schema_config.py (517)
- tests/contracts/test_schema_contract.py (1023)

### Batch 17 (5 files, 889 lines)
- tests/contracts/test_schema_contract_factory.py (177)
- tests/contracts/test_source_row_contract.py (80)
- tests/contracts/test_telemetry_config.py (356)
- tests/contracts/test_token_info_pipeline_row.py (88)
- tests/contracts/test_transform_contract.py (184)

### Batch 18 (5 files, 816 lines)
- tests/contracts/test_transform_result_contract.py (188)
- tests/contracts/test_type_normalization.py (275)
- tests/contracts/test_update_schemas.py (77)
- tests/contracts/transform_contracts/test_azure_content_safety_contract.py (92)
- tests/contracts/transform_contracts/test_azure_multi_query_contract.py (164)

### Batch 19 (5 files, 1376 lines)
- tests/contracts/transform_contracts/test_azure_prompt_shield_contract.py (87)
- tests/contracts/transform_contracts/test_batch_transform_protocol.py (506)
- tests/contracts/transform_contracts/test_keyword_filter_contract.py (58)
- tests/contracts/transform_contracts/test_passthrough_contract.py (201)
- tests/contracts/transform_contracts/test_transform_protocol.py (424)

### Batch 20 (2 files, 201 lines)
- tests/contracts/transform_contracts/test_truncate_contract.py (102)
- tests/contracts/transform_contracts/test_web_scrape_contract.py (99)

### Batch 21 (3 files, 1451 lines)
- tests/core/checkpoint/test_checkpoint_contracts.py (362)
- tests/core/checkpoint/test_compatibility_validator.py (711)
- tests/core/checkpoint/test_manager.py (578 - SKIP)

### Batch 22 (2 files, 965 lines)
- tests/core/checkpoint/test_manager.py (578)
- tests/core/checkpoint/test_manager_mutation_gaps.py (387)

### Batch 23 (1 file, 794 lines)
- tests/core/checkpoint/test_recovery.py (794)

### Batch 24 (1 file, 1233 lines)
- tests/core/checkpoint/test_recovery_fork_partial.py (1233)

### Batch 25 (3 files, 1327 lines)
- tests/core/checkpoint/test_recovery_multi_sink.py (409)
- tests/core/checkpoint/test_recovery_mutation_gaps.py (694)
- tests/core/checkpoint/test_recovery_row_data.py (297 - SKIP)

### Batch 26 (3 files, 918 lines)
- tests/core/checkpoint/test_recovery_row_data.py (297)
- tests/core/checkpoint/test_recovery_type_fidelity.py (224)
- tests/core/checkpoint/test_topology_validation.py (397)

### Batch 27 (5 files, 847 lines)
- tests/core/landscape/test_artifact_repository.py (99)
- tests/core/landscape/test_database.py (537)
- tests/core/landscape/test_database_ops.py (49)
- tests/core/landscape/test_error_repositories.py (262 - SKIP)

### Batch 28 (2 files, 771 lines)
- tests/core/landscape/test_error_repositories.py (262)
- tests/core/landscape/test_error_table_foreign_keys.py (509)

### Batch 29 (5 files, 1905 lines)
- tests/core/landscape/test_exports.py (121)
- tests/core/landscape/test_exporter.py (1265)
- tests/core/landscape/test_formatters.py (520 - SKIP)

### Batch 30 (3 files, 1242 lines)
- tests/core/landscape/test_formatters.py (520)
- tests/core/landscape/test_helpers.py (69)
- tests/core/landscape/test_lineage.py (653)

### Batch 31 (4 files, 1559 lines)
- tests/core/landscape/test_lineage_mutation_gaps.py (236)
- tests/core/landscape/test_models_enums.py (182)
- tests/core/landscape/test_models_mutation_gaps.py (905)
- tests/core/landscape/test_node_state_repository.py (509 - SKIP)

### Batch 32 (2 files, 1910 lines)
- tests/core/landscape/test_node_state_repository.py (509)
- tests/core/landscape/test_operations.py (1401)

### Batch 33 (4 files, 1583 lines)
- tests/core/landscape/test_recorder_artifacts.py (341)
- tests/core/landscape/test_recorder_batches.py (449)
- tests/core/landscape/test_recorder_calls.py (734)

### Batch 34 (2 files, 1172 lines)
- tests/core/landscape/test_recorder_contracts.py (836)
- tests/core/landscape/test_recorder_errors.py (336)

### Batch 35 (4 files, 1679 lines)
- tests/core/landscape/test_recorder_explain.py (348)
- tests/core/landscape/test_recorder_grades.py (323)
- tests/core/landscape/test_recorder_nodes.py (387)
- tests/core/landscape/test_recorder_node_states.py (621)

### Batch 36 (4 files, 1031 lines)
- tests/core/landscape/test_recorder_queries.py (218)
- tests/core/landscape/test_recorder_routing_events.py (332)
- tests/core/landscape/test_recorder_row_data.py (259)
- tests/core/landscape/test_recorder_runs.py (296 - SKIP)

### Batch 37 (3 files, 1345 lines)
- tests/core/landscape/test_recorder_runs.py (296)
- tests/core/landscape/test_recorder_tokens.py (753)
- tests/core/landscape/test_repositories.py (734 - SKIP)

### Batch 38 (2 files, 991 lines)
- tests/core/landscape/test_repositories.py (734)
- tests/core/landscape/test_reproducibility.py (257)

### Batch 39 (5 files, 858 lines)
- tests/core/landscape/test_routing.py (39)
- tests/core/landscape/test_row_data.py (64)
- tests/core/landscape/test_schema.py (232)
- tests/core/landscape/test_schema_contracts_schema.py (204)
- tests/core/landscape/test_secret_resolutions.py (318)

### Batch 40 (3 files, 1318 lines)
- tests/core/landscape/test_token_outcome_constraints.py (341)
- tests/core/landscape/test_validation_error_noncanonical.py (379)
- tests/core/rate_limit/test_limiter.py (598)

### Batch 41 (1 file, 328 lines)
- tests/core/rate_limit/test_registry.py (328)

### Batch 42 (1 file, 2425 lines) **OVERSIZED - SINGLE FILE**
- tests/core/retention/test_purge.py (2425)

### Batch 43 (2 files, 1191 lines)
- tests/core/security/test_config_secrets.py (618)
- tests/core/security/test_fingerprint.py (90)
- tests/core/security/test_fingerprint_keyvault.py (224)
- tests/core/security/test_secret_loader.py (573 - SKIP)

### Batch 44 (2 files, 1065 lines)
- tests/core/security/test_secret_loader.py (573)
- tests/core/security/test_url.py (492)

### Batch 45 (1 file, 99 lines)
- tests/core/security/test_web.py (99)

### Batch 46 (4 files, 1243 lines)
- tests/core/test_canonical.py (450)
- tests/core/test_canonical_mutation_gaps.py (157)
- tests/core/test_config.py (3106 - SKIP, OVERSIZED)

### Batch 47 (1 file, 3106 lines) **OVERSIZED - SINGLE FILE**
- tests/core/test_config.py (3106)

### Batch 48 (3 files, 1339 lines)
- tests/core/test_config_aggregation.py (318)
- tests/core/test_config_alignment.py (956)
- tests/core/test_config_single_rejected.py (65)

### Batch 49 (1 file, 3508 lines) **OVERSIZED - SINGLE FILE**
- tests/core/test_dag.py (3508)

### Batch 50 (2 files, 1295 lines)
- tests/core/test_dag_contract_validation.py (860)
- tests/core/test_dag_schema_propagation.py (475 - SKIP)

### Batch 51 (3 files, 1146 lines)
- tests/core/test_dag_schema_propagation.py (475)
- tests/core/test_edge_validation.py (435)
- tests/core/test_events.py (236)

### Batch 52 (5 files, 757 lines)
- tests/core/test_identifiers.py (52)
- tests/core/test_logging.py (146)
- tests/core/test_payload_store.py (339)
- tests/core/test_secrets_config.py (123)
- tests/core/test_template_extraction_dual.py (97)

### Batch 53 (2 files, 797 lines)
- tests/core/test_templates.py (199)
- tests/core/test_token_outcomes.py (598)

### Batch 54 (2 files, 342 lines)
- tests/engine/orchestrator/test_export.py (193)
- tests/engine/orchestrator/test_types.py (149)

### Batch 55 (1 file, 897 lines)
- tests/engine/test_aggregation_audit.py (897)

### Batch 56 (1 file, 1748 lines)
- tests/engine/test_aggregation_executor.py (1748)

### Batch 57 (1 file, 3228 lines) **OVERSIZED - SINGLE FILE**
- tests/engine/test_aggregation_integration.py (3228)

### Batch 58 (2 files, 1322 lines)
- tests/engine/test_audit_sweep.py (920)
- tests/engine/test_batch_adapter.py (402)

### Batch 59 (3 files, 1181 lines)
- tests/engine/test_batch_audit_trail.py (411)
- tests/engine/test_batch_token_identity.py (365)
- tests/engine/test_checkpoint_durability.py (1203 - SKIP)

### Batch 60 (1 file, 1203 lines)
- tests/engine/test_checkpoint_durability.py (1203)

### Batch 61 (2 files, 1998 lines)
- tests/engine/test_coalesce_contract_bug.py (83)
- tests/engine/test_coalesce_executor.py (1915)

### Batch 62 (2 files, 1808 lines)
- tests/engine/test_coalesce_executor_audit_gaps.py (621)
- tests/engine/test_coalesce_integration.py (1187)

### Batch 63 (3 files, 1635 lines)
- tests/engine/test_coalesce_pipeline_row.py (396)
- tests/engine/test_completed_outcome_timing.py (407)
- tests/engine/test_config_gates.py (832)

### Batch 64 (1 file, 1718 lines)
- tests/engine/test_engine_gates.py (1718)

### Batch 65 (2 files, 1175 lines)
- tests/engine/test_executor_batch_integration.py (584)
- tests/engine/test_executors.py (1591 - SKIP)

### Batch 66 (2 files, 2015 lines) **SLIGHTLY OVER**
- tests/engine/test_executor_pipeline_row.py (1424)
- tests/engine/test_executors.py (1591 - SKIP)

### Batch 67 (1 file, 1591 lines)
- tests/engine/test_executors.py (1591)

### Batch 68 (1 file, 1424 lines)
- tests/engine/test_executor_pipeline_row.py (1424)

### Batch 69 (2 files, 1763 lines)
- tests/engine/test_expression_parser.py (1363)
- tests/engine/test_gate_executor.py (1452 - SKIP)

### Batch 70 (2 files, 1477 lines)
- tests/engine/test_gate_executor.py (1452)
- tests/engine/test_group_id_consistency.py (700 - SKIP)

### Batch 71 (2 files, 1700 lines)
- tests/engine/test_group_id_consistency.py (700)
- tests/engine/test_integration.py (3696 - SKIP, OVERSIZED)

### Batch 72 (1 file, 3696 lines) **OVERSIZED - SINGLE FILE**
- tests/engine/test_integration.py (3696)

### Batch 73 (5 files, 988 lines)
- tests/engine/test_join_group_id_bug.py (25)
- tests/engine/test_multiple_coalesces.py (116)
- tests/engine/test_node_id_assignment.py (220)
- tests/engine/test_orchestrator_audit.py (1424 - SKIP)

### Batch 74 (1 file, 1424 lines)
- tests/engine/test_orchestrator_audit.py (1424)

### Batch 75 (3 files, 1726 lines)
- tests/engine/test_orchestrator_checkpointing.py (718)
- tests/engine/test_orchestrator_cleanup.py (276)
- tests/engine/test_orchestrator_contracts.py (732)

### Batch 76 (2 files, 1491 lines)
- tests/engine/test_orchestrator_core.py (694)
- tests/engine/test_orchestrator_errors.py (797)

### Batch 77 (3 files, 1694 lines)
- tests/engine/test_orchestrator_field_resolution.py (280)
- tests/engine/test_orchestrator_fork_coalesce.py (866)
- tests/engine/test_orchestrator_lifecycle.py (548)

### Batch 78 (2 files, 951 lines)
- tests/engine/test_orchestrator_mutation_gaps.py (564)
- tests/engine/test_orchestrator_payload_store.py (387)

### Batch 79 (4 files, 1179 lines)
- tests/engine/test_orchestrator_phase_events.py (240)
- tests/engine/test_orchestrator_progress.py (376)
- tests/engine/test_orchestrator_recovery.py (323)
- tests/engine/test_orchestrator_resume.py (1016 - SKIP)

### Batch 80 (2 files, 1266 lines)
- tests/engine/test_orchestrator_resume.py (1016)
- tests/engine/test_orchestrator_retry.py (250)

### Batch 81 (2 files, 1347 lines)
- tests/engine/test_orchestrator_routing.py (619)
- tests/engine/test_orchestrator_telemetry.py (728)

### Batch 82 (2 files, 760 lines)
- tests/engine/test_orchestrator_validation.py (524)
- tests/engine/test_plugin_detection.py (236)

### Batch 83 (2 files, 1504 lines)
- tests/engine/test_processor_batch.py (931)
- tests/engine/test_processor_coalesce.py (1735 - SKIP)

### Batch 84 (1 file, 1735 lines)
- tests/engine/test_processor_coalesce.py (1735)

### Batch 85 (3 files, 1341 lines)
- tests/engine/test_processor_core.py (573)
- tests/engine/test_processor_gates.py (505)
- tests/engine/test_processor_guards.py (263)

### Batch 86 (2 files, 1840 lines)
- tests/engine/test_processor_modes.py (1144)
- tests/engine/test_processor_mutation_gaps.py (1153 - SKIP)

### Batch 87 (2 files, 1849 lines)
- tests/engine/test_processor_mutation_gaps.py (1153)
- tests/engine/test_processor_outcomes.py (696)

### Batch 88 (4 files, 1662 lines)
- tests/engine/test_processor_pipeline_row.py (182)
- tests/engine/test_processor_quarantine.py (245)
- tests/engine/test_processor_retry.py (740)
- tests/engine/test_processor_telemetry.py (1165 - SKIP)

### Batch 89 (2 files, 1396 lines)
- tests/engine/test_processor_telemetry.py (1165)
- tests/engine/test_retry.py (231)

### Batch 90 (4 files, 1515 lines)
- tests/engine/test_retry_policy.py (226)
- tests/engine/test_routing_enums.py (332)
- tests/engine/test_row_outcome.py (118)
- tests/engine/test_run_status.py (27)
- tests/engine/test_sink_executor.py (721)

### Batch 91 (3 files, 2164 lines) **SLIGHTLY OVER**
- tests/engine/test_spans.py (839)
- tests/engine/test_token_manager_pipeline_row.py (333)
- tests/engine/test_tokens.py (992)

### Batch 92 (3 files, 1783 lines)
- tests/engine/test_transform_error_routing.py (637)
- tests/engine/test_transform_executor.py (885)
- tests/engine/test_transform_success_reason.py (261)

### Batch 93 (2 files, 815 lines)
- tests/engine/test_triggers.py (591)
- tests/examples/test_llm_examples.py (224)

### Batch 94 (3 files, 1305 lines)
- tests/integration/test_aggregation_checkpoint_bug_reproduction.py (297)
- tests/integration/test_aggregation_contracts.py (471)
- tests/integration/test_aggregation_recovery.py (577 - SKIP)

### Batch 95 (2 files, 814 lines)
- tests/integration/test_aggregation_recovery.py (577)
- tests/integration/test_audit_integration_fixes.py (237)

### Batch 96 (2 files, 1380 lines)
- tests/integration/test_chaosllm_server.py (640)
- tests/integration/test_checkpoint_recovery.py (740)

### Batch 97 (5 files, 801 lines)
- tests/integration/test_checkpoint_version_validation.py (186)
- tests/integration/test_cli_integration.py (246)
- tests/integration/test_cli_resume.py (62)
- tests/integration/test_cli_resume_schema_validation.py (362 - SKIP)

### Batch 98 (3 files, 683 lines)
- tests/integration/test_cli_resume_schema_validation.py (362)
- tests/integration/test_cli_resume_sink_capability.py (215)
- tests/integration/test_cli_schema_validation.py (106)

### Batch 99 (3 files, 1460 lines)
- tests/integration/test_concurrency_integration.py (262)
- tests/integration/test_contract_audit_integration.py (655)
- tests/integration/test_deaggregation.py (411)
- tests/integration/test_error_event_persistence.py (543 - SKIP)

### Batch 100 (2 files, 673 lines)
- tests/integration/test_error_event_persistence.py (543)
- tests/integration/test_keyvault_fingerprint.py (130)

### Batch 101 (2 files, 785 lines)
- tests/integration/test_landscape_export.py (436)
- tests/integration/test_llm_contract_validation.py (349)

### Batch 102 (1 file, 1030 lines)
- tests/integration/test_llm_transforms.py (1030)

### Batch 103 (3 files, 1183 lines)
- tests/integration/test_multi_query_integration.py (365)
- tests/integration/test_rate_limit_integration.py (409)
- tests/integration/test_resume_comprehensive.py (1422 - SKIP)

### Batch 104 (1 file, 1422 lines)
- tests/integration/test_resume_comprehensive.py (1422)

### Batch 105 (5 files, 1560 lines)
- tests/integration/test_resume_edge_ids.py (294)
- tests/integration/test_resume_schema_required.py (193)
- tests/integration/test_retry_integration.py (746)
- tests/integration/test_schema_not_null_constraints.py (220)

### Batch 106 (4 files, 1232 lines)
- tests/integration/test_schema_validation_end_to_end.py (403)
- tests/integration/test_schema_validation_integration.py (256)
- tests/integration/test_schema_validation_regression.py (150)
- tests/integration/test_sink_durability.py (423)

### Batch 107 (4 files, 1477 lines)
- tests/integration/test_source_contract_integration.py (423)
- tests/integration/test_source_payload_storage.py (187)
- tests/integration/test_telemetry_wiring.py (371)
- tests/integration/test_template_resolver_integration.py (590 - SKIP)

### Batch 108 (2 files, 1046 lines)
- tests/integration/test_template_resolver_integration.py (590)
- tests/integration/test_transform_contract_integration.py (456)

### Batch 109 (3 files, 965 lines)
- tests/mcp/test_contract_tools.py (458)
- tests/performance/test_baseline_schema_validation.py (200)
- tests/performance/test_token_expansion_performance.py (307)

### Batch 110 (3 files, 544 lines)
- tests/plugins/azure/test_auth.py (362)
- tests/plugins/azure/test_blob_emulator_integration.py (150)
- tests/plugins/azure/test_blob_sink.py (987 - SKIP)

### Batch 111 (2 files, 1019 lines)
- tests/plugins/azure/test_blob_sink.py (987)
- tests/plugins/azure/test_blob_sink_resume.py (32)

### Batch 112 (1 file, 881 lines)
- tests/plugins/azure/test_blob_source.py (881)

### Batch 113 (2 files, 826 lines)
- tests/plugins/batching/test_batch_transform_mixin.py (468)
- tests/plugins/batching/test_row_reorder_buffer.py (358)

### Batch 114 (5 files, 1306 lines)
- tests/plugins/clients/test_audited_client_base.py (102)
- tests/plugins/clients/test_audited_http_client.py (1289 - SKIP)

### Batch 115 (1 file, 1289 lines)
- tests/plugins/clients/test_audited_http_client.py (1289)

### Batch 116 (3 files, 1498 lines)
- tests/plugins/clients/test_audited_llm_client.py (672)
- tests/plugins/clients/test_http.py (483)
- tests/plugins/clients/test_http_telemetry.py (449 - SKIP)

### Batch 117 (3 files, 1172 lines)
- tests/plugins/clients/test_http_telemetry.py (449)
- tests/plugins/clients/test_llm_error_classification.py (343)
- tests/plugins/clients/test_llm_telemetry.py (380)

### Batch 118 (2 files, 1489 lines)
- tests/plugins/clients/test_replayer.py (552)
- tests/plugins/clients/test_verifier.py (937)

### Batch 119 (5 files, 905 lines)
- tests/plugins/config/test_tabular_source_config.py (173)
- tests/plugins/llm/test_aimd_throttle.py (187)
- tests/plugins/llm/test_azure.py (1002 - SKIP)

### Batch 120 (1 file, 1002 lines)
- tests/plugins/llm/test_azure.py (1002)

### Batch 121 (1 file, 1569 lines)
- tests/plugins/llm/test_azure_batch.py (1569)

### Batch 122 (2 files, 1392 lines)
- tests/plugins/llm/test_azure_batch_audit_integration.py (491)
- tests/plugins/llm/test_azure_multi_query.py (901)

### Batch 123 (2 files, 1697 lines)
- tests/plugins/llm/test_azure_multi_query_profiling.py (823)
- tests/plugins/llm/test_azure_multi_query_retry.py (874)

### Batch 124 (4 files, 1477 lines)
- tests/plugins/llm/test_azure_tracing.py (432)
- tests/plugins/llm/test_base.py (666)
- tests/plugins/llm/test_batch_errors.py (181)
- tests/plugins/llm/test_batch_single_row_contract.py (204 - SKIP)

### Batch 125 (5 files, 896 lines)
- tests/plugins/llm/test_batch_single_row_contract.py (204)
- tests/plugins/llm/test_capacity_errors.py (58)
- tests/plugins/llm/test_contract_aware_template.py (185)
- tests/plugins/llm/test_llm_transform_contract.py (247)
- tests/plugins/llm/test_multi_query.py (677 - SKIP)

### Batch 126 (2 files, 879 lines)
- tests/plugins/llm/test_multi_query.py (677)
- tests/plugins/llm/test_openrouter.py (1695 - SKIP)

### Batch 127 (1 file, 1695 lines)
- tests/plugins/llm/test_openrouter.py (1695)

### Batch 128 (2 files, 1643 lines)
- tests/plugins/llm/test_openrouter_batch.py (669)
- tests/plugins/llm/test_openrouter_multi_query.py (974)

### Batch 129 (4 files, 1561 lines)
- tests/plugins/llm/test_openrouter_tracing.py (501)
- tests/plugins/llm/test_pool_config.py (202)
- tests/plugins/llm/test_pooled_executor.py (848)

### Batch 130 (5 files, 1020 lines)
- tests/plugins/llm/test_prompt_template_contract.py (190)
- tests/plugins/llm/test_reorder_buffer.py (212)
- tests/plugins/llm/test_templates.py (236)
- tests/plugins/llm/test_tracing_config.py (144)
- tests/plugins/llm/test_tracing_integration.py (620 - SKIP)

### Batch 131 (2 files, 989 lines)
- tests/plugins/llm/test_tracing_integration.py (620)
- tests/plugins/pooling/test_executor_retryable_errors.py (369)

### Batch 132 (3 files, 854 lines)
- tests/plugins/sinks/test_csv_sink.py (474)
- tests/plugins/sinks/test_csv_sink_append.py (337)
- tests/plugins/sinks/test_csv_sink_headers.py (434 - SKIP)

### Batch 133 (3 files, 1201 lines)
- tests/plugins/sinks/test_csv_sink_headers.py (434)
- tests/plugins/sinks/test_csv_sink_resume.py (43)
- tests/plugins/sinks/test_database_sink.py (724)

### Batch 134 (4 files, 1255 lines)
- tests/plugins/sinks/test_database_sink_resume.py (57)
- tests/plugins/sinks/test_json_sink.py (222)
- tests/plugins/sinks/test_json_sink_resume.py (130)
- tests/plugins/sinks/test_sink_display_headers.py (846)

### Batch 135 (2 files, 551 lines)
- tests/plugins/sinks/test_sink_protocol_compliance.py (61)
- tests/plugins/sinks/test_sink_schema_validation_common.py (490)

### Batch 136 (3 files, 1784 lines)
- tests/plugins/sources/test_csv_source.py (709)
- tests/plugins/sources/test_csv_source_contract.py (196)
- tests/plugins/sources/test_field_normalization.py (365)
- tests/plugins/sources/test_json_source.py (901 - SKIP)

### Batch 137 (2 files, 977 lines)
- tests/plugins/sources/test_json_source.py (901)
- tests/plugins/sources/test_null_source.py (76)

### Batch 138 (5 files, 552 lines)
- tests/plugins/test_base.py (332)
- tests/plugins/test_base_signatures.py (26)
- tests/plugins/test_base_sink.py (35)
- tests/plugins/test_base_sink_contract.py (87)
- tests/plugins/test_base_source_contract.py (69)

### Batch 139 (4 files, 1383 lines)
- tests/plugins/test_builtin_plugin_metadata.py (127)
- tests/plugins/test_config_base.py (427)
- tests/plugins/test_context.py (704)
- tests/plugins/test_context_types.py (74)

### Batch 140 (5 files, 996 lines)
- tests/plugins/test_discovery.py (425)
- tests/plugins/test_enums.py (62)
- tests/plugins/test_hookimpl_registration.py (76)
- tests/plugins/test_hookspecs.py (33)
- tests/plugins/test_integration.py (175)
- tests/plugins/test_manager.py (291 - SKIP)

### Batch 141 (4 files, 1256 lines)
- tests/plugins/test_manager.py (291)
- tests/plugins/test_node_id_protocol.py (171)
- tests/plugins/test_protocol_lifecycle.py (119)
- tests/plugins/test_protocols.py (675)

### Batch 142 (5 files, 1603 lines)
- tests/plugins/test_results.py (370)
- tests/plugins/test_schema_factory.py (514)
- tests/plugins/test_schemas.py (382)
- tests/plugins/test_sink_header_config.py (207)
- tests/plugins/test_utils.py (81)

### Batch 143 (3 files, 1610 lines)
- tests/plugins/test_validation.py (329)
- tests/plugins/test_validation_integration.py (97)
- tests/plugins/transforms/azure/test_content_safety.py (1184)

### Batch 144 (1 file, 1108 lines)
- tests/plugins/transforms/azure/test_prompt_shield.py (1108)

### Batch 145 (5 files, 1353 lines)
- tests/plugins/transforms/test_batch_replicate.py (296)
- tests/plugins/transforms/test_batch_replicate_integration.py (105)
- tests/plugins/transforms/test_batch_stats.py (165)
- tests/plugins/transforms/test_batch_stats_integration.py (126)
- tests/plugins/transforms/test_field_mapper.py (380)
- tests/plugins/transforms/test_json_explode.py (488 - SKIP)

### Batch 146 (2 files, 851 lines)
- tests/plugins/transforms/test_json_explode.py (488)
- tests/plugins/transforms/test_keyword_filter.py (363)

### Batch 147 (4 files, 1255 lines)
- tests/plugins/transforms/test_passthrough.py (181)
- tests/plugins/transforms/test_web_scrape.py (631)
- tests/plugins/transforms/test_web_scrape_errors.py (93)
- tests/plugins/transforms/test_web_scrape_extraction.py (110)
- tests/plugins/transforms/test_web_scrape_fingerprint.py (47)
- tests/plugins/transforms/test_web_scrape_properties.py (331 - SKIP)

### Batch 148 (2 files, 506 lines)
- tests/plugins/transforms/test_web_scrape_fingerprint.py (47)
- tests/plugins/transforms/test_web_scrape_properties.py (331)
- tests/plugins/transforms/test_web_scrape_security.py (175 - SKIP)

### Batch 149 (1 file, 175 lines)
- tests/plugins/transforms/test_web_scrape_security.py (175)

### Batch 150 (3 files, 1541 lines)
- tests/property/audit/test_fork_coalesce_flow.py (590)
- tests/property/audit/test_fork_join_balance.py (683)
- tests/property/audit/test_recorder_properties.py (1080 - SKIP)

### Batch 151 (2 files, 1458 lines)
- tests/property/audit/test_recorder_properties.py (1080)
- tests/property/audit/test_terminal_states.py (378)

### Batch 152 (2 files, 649 lines)
- tests/property/canonical/test_hash_determinism.py (366)
- tests/property/canonical/test_nan_rejection.py (283)

### Batch 153 (2 files, 785 lines)
- tests/property/contracts/test_serialization_properties.py (558)
- tests/property/contracts/test_validation_rejection_properties.py (227)

### Batch 154 (2 files, 1529 lines)
- tests/property/core/test_checkpoint_properties.py (740)
- tests/property/core/test_dag_properties.py (789)

### Batch 155 (4 files, 1269 lines)
- tests/property/core/test_fingerprint_properties.py (304)
- tests/property/core/test_helpers_properties.py (298)
- tests/property/core/test_identifiers_properties.py (363)
- tests/property/core/test_lineage_properties.py (354 - SKIP)

### Batch 156 (3 files, 921 lines)
- tests/property/core/test_lineage_properties.py (354)
- tests/property/core/test_payload_store_properties.py (213)
- tests/property/core/test_rate_limiter_properties.py (446 - SKIP)

### Batch 157 (2 files, 849 lines)
- tests/property/core/test_rate_limiter_properties.py (446)
- tests/property/core/test_rate_limiter_state_machine.py (403)

### Batch 158 (3 files, 1058 lines)
- tests/property/core/test_reproducibility_properties.py (376)
- tests/property/core/test_row_data_properties.py (272)
- tests/property/core/test_templates_properties.py (410)

### Batch 159 (4 files, 1787 lines)
- tests/property/engine/test_aggregation_state_properties.py (201)
- tests/property/engine/test_clock_properties.py (336)
- tests/property/engine/test_coalesce_properties.py (766)
- tests/property/engine/test_executor_properties.py (484)

### Batch 160 (2 files, 1353 lines)
- tests/property/engine/test_processor_properties.py (900)
- tests/property/engine/test_retry_properties.py (453)

### Batch 161 (2 files, 1087 lines)
- tests/property/engine/test_token_lifecycle_state_machine.py (736)
- tests/property/engine/test_token_properties.py (351)

### Batch 162 (4 files, 895 lines)
- tests/property/integration/test_cross_module_properties.py (191)
- tests/property/plugins/llm/test_response_validation_properties.py (182)
- tests/property/plugins/test_schema_coercion_properties.py (436)
- tests/property/sinks/test_csv_sink_properties.py (127 - SKIP)

### Batch 163 (3 files, 324 lines)
- tests/property/sinks/test_csv_sink_properties.py (127)
- tests/property/sinks/test_database_sink_properties.py (85)
- tests/property/sinks/test_json_sink_properties.py (112)

### Batch 164 (3 files, 1099 lines)
- tests/property/sources/test_field_normalization_properties.py (302)
- tests/scripts/cicd/test_enforce_tier_model.py (652)
- tests/scripts/test_check_contracts.py (1447 - SKIP)

### Batch 165 (2 files, 1592 lines)
- tests/scripts/test_check_contracts.py (1447)
- tests/scripts/test_validate_deployment.py (145)

### Batch 166 (1 file, 532 lines) - **AUDITED**
- tests/spikes/test_nodeinfo_typed_config_spikes.py (532)
- **Audit:** docs/test_audit/spikes/test_nodeinfo_typed_config_spikes.py.audit.md
- **Score:** 9/10 - Well-designed spike tests

### Batch 167 (3 files, 1322 lines) - **AUDITED**
- tests/stress/llm/test_azure_llm_stress.py (420)
- tests/stress/llm/test_azure_multi_query_stress.py (375)
- tests/stress/llm/test_mixed_errors.py (527)
- **Audit:** docs/test_audit/stress/llm_stress_tests.audit.md (combined with Batch 168)
- **Score:** 7/10 - Good stress tests but significant code duplication

### Batch 168 (2 files, 771 lines) - **AUDITED**
- tests/stress/llm/test_openrouter_llm_stress.py (344)
- tests/stress/llm/test_openrouter_multi_query_stress.py (427)
- **Audit:** docs/test_audit/stress/llm_stress_tests.audit.md (combined with Batch 167)
- **Score:** 7/10 - Good stress tests but significant code duplication

### Batch 169 (2 files, 1524 lines) - **AUDITED**
- tests/system/audit_verification/test_lineage_completeness.py (495)
- tests/system/recovery/test_crash_recovery.py (1029)
- **Audits:**
  - docs/test_audit/system/test_lineage_completeness.py.audit.md (8/10)
  - docs/test_audit/system/test_crash_recovery.py.audit.md (7/10)

### Batch 170 (4 files, 1418 lines)
- tests/telemetry/exporters/test_azure_monitor.py (370)
- tests/telemetry/exporters/test_azure_monitor_integration.py (331)
- tests/telemetry/exporters/test_console.py (89)
- tests/telemetry/exporters/test_datadog.py (636 - SKIP)

### Batch 171 (2 files, 1069 lines)
- tests/telemetry/exporters/test_datadog.py (636)
- tests/telemetry/exporters/test_datadog_integration.py (433)

### Batch 172 (2 files, 1038 lines)
- tests/telemetry/exporters/test_otlp.py (648)
- tests/telemetry/exporters/test_otlp_integration.py (390)

### Batch 173 (3 files, 1485 lines)
- tests/telemetry/test_contracts.py (449)
- tests/telemetry/test_integration.py (886)
- tests/telemetry/test_plugin_wiring.py (150)

### Batch 174 (2 files, 1364 lines)
- tests/telemetry/test_property_based.py (866)
- tests/telemetry/test_reentrance.py (498)

### Batch 175 (3 files, 1803 lines)
- tests/testing/chaosllm/test_error_injector.py (803)
- tests/testing/chaosllm/test_fixture.py (230)
- tests/testing/chaosllm/test_latency_simulator.py (339)
- tests/testing/chaosllm/test_metrics.py (1151 - SKIP)

### Batch 176 (1 file, 1151 lines)
- tests/testing/chaosllm/test_metrics.py (1151)

### Batch 177 (3 files, 2069 lines) **SLIGHTLY OVER**
- tests/testing/chaosllm/test_response_generator.py (867)
- tests/testing/chaosllm/test_server.py (694)
- tests/testing/chaosllm_mcp/test_server.py (508)

### Batch 178 (5 files, 919 lines)
- tests/tui/test_constants.py (69)
- tests/tui/test_explain_app.py (170)
- tests/tui/test_graceful_degradation.py (257)
- tests/tui/test_lineage_tree.py (160)
- tests/tui/test_lineage_types.py (170)
- tests/tui/test_node_detail.py (253 - SKIP)

### Batch 179 (1 file, 253 lines)
- tests/tui/test_node_detail.py (253)

### Batch 180 (2 files, 516 lines)
- tests/unit/chaosllm/test_config.py (447)
- tests/unit/plugins/llm/test_metadata_fields.py (69)

### Batch 181 (2 files, 668 lines)
- tests/unit/plugins/transforms/test_truncate.py (246)
- tests/unit/telemetry/test_buffer.py (422)

### Batch 182 (2 files, 1217 lines)
- tests/unit/telemetry/test_console_exporter.py (698)
- tests/unit/telemetry/test_events.py (519)

### Batch 183 (3 files, 1793 lines)
- tests/unit/telemetry/test_factory.py (125)
- tests/unit/telemetry/test_filtering.py (426)
- tests/unit/telemetry/test_manager.py (1242)

---

## Summary

| Metric | Value |
|--------|-------|
| Total Files | 434 |
| Total Lines | 209,464 |
| Total Batches | 183 |
| Oversized Files (>2000 lines) | 5 |
| Average Batch Size | 1,145 lines |

### Batches by Category

| Directory | Files | Lines | Batches |
|-----------|-------|-------|---------|
| tests/audit | 1 | 461 | 1 |
| tests/cli | 14 | 5,325 | 6 |
| tests/contracts | 55 | 14,744 | 20 |
| tests/core | 84 | 39,138 | 44 |
| tests/engine | 78 | 56,889 | 44 |
| tests/examples | 1 | 224 | 1 |
| tests/integration | 38 | 14,660 | 16 |
| tests/mcp | 1 | 458 | 1 |
| tests/performance | 2 | 507 | 1 |
| tests/plugins | 97 | 38,287 | 33 |
| tests/property | 32 | 14,125 | 14 |
| tests/scripts | 3 | 2,244 | 2 |
| tests/spikes | 1 | 532 | 1 |
| tests/stress | 5 | 2,093 | 2 |
| tests/system | 2 | 1,524 | 1 |
| tests/telemetry | 13 | 6,574 | 5 |
| tests/testing | 8 | 4,930 | 3 |
| tests/tui | 6 | 1,079 | 2 |
| tests/unit | 12 | 5,870 | 4 |
