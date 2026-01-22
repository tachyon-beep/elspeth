# Mutation Testing Gaps Checklist

**Generated:** 2026-01-23
**Progress:** 1,603 / 2,723 mutants tested (59%)
**Kill Rate:** 79.9%
**Actionable Survivors:** 113 (excluding schema.py)

Use this checklist to systematically address surviving mutants.
Each survivor represents a line where a bug could hide undetected.

---

## Quick Reference

| Priority | File | Survivors | Why It Matters |
|----------|------|-----------|----------------|
| P1 | `engine/orchestrator.py` | 48 | Critical orchestration logic |
| P2 | `core/landscape/models.py` | 36 | Audit data models |
| P1 | `core/checkpoint/recovery.py` | 13 | Pipeline recovery - must be reliable |
| P2 | `core/checkpoint/manager.py` | 2 | Checkpoint persistence |
| P2 | `core/canonical.py` | 1 | Hash integrity |
| P2 | `core/landscape/lineage.py` | 1 | Lineage queries |

---

## engine/orchestrator.py

**Priority:** P1 — Critical orchestration logic
**Survivors:** 48 unique lines (58 total mutants)

### Line 36 (2 mutants)

```python
      34 | # Type alias for row-processing plugins in the transforms pipeline
      35 | # NOTE: BaseAggregation was DELETED - aggregation is now handled by
>>>   36 | # batch-aware transforms (is_batch_aware=True on BaseTransform)
      37 | RowPlugin = BaseTransform | BaseGate
      38 | """Union of all row-processing plugin types for pipeline transforms list."""
```

- [ ] Add test to catch mutations on this line

### Line 67

```python
      65 |     sinks: dict[str, SinkProtocol]  # Sinks implement batch write directly
      66 |     config: dict[str, Any] = field(default_factory=dict)
>>>   67 |     gates: list[GateSettings] = field(default_factory=list)
      68 |     aggregation_settings: dict[str, AggregationSettings] = field(default_factory=dict)
      69 |     coalesce_settings: list[CoalesceSettings] = field(default_factory=list)
```

- [ ] Add test to catch mutations on this line

### Line 68

```python
      66 |     config: dict[str, Any] = field(default_factory=dict)
      67 |     gates: list[GateSettings] = field(default_factory=list)
>>>   68 |     aggregation_settings: dict[str, AggregationSettings] = field(default_factory=dict)
      69 |     coalesce_settings: list[CoalesceSettings] = field(default_factory=list)
      70 |
```

- [ ] Add test to catch mutations on this line

### Line 81 (2 mutants)

```python
      79 |     rows_succeeded: int
      80 |     rows_failed: int
>>>   81 |     rows_routed: int
      82 |     rows_quarantined: int = 0
      83 |     rows_forked: int = 0
```

- [ ] Add test to catch mutations on this line

### Line 82 (2 mutants)

```python
      80 |     rows_failed: int
      81 |     rows_routed: int
>>>   82 |     rows_quarantined: int = 0
      83 |     rows_forked: int = 0
      84 |     rows_coalesced: int = 0
```

- [ ] Add test to catch mutations on this line

### Line 83 (2 mutants)

```python
      81 |     rows_routed: int
      82 |     rows_quarantined: int = 0
>>>   83 |     rows_forked: int = 0
      84 |     rows_coalesced: int = 0
      85 |     rows_expanded: int = 0  # Deaggregation parent tokens
```

- [ ] Add test to catch mutations on this line

### Line 84 (2 mutants)

```python
      82 |     rows_quarantined: int = 0
      83 |     rows_forked: int = 0
>>>   84 |     rows_coalesced: int = 0
      85 |     rows_expanded: int = 0  # Deaggregation parent tokens
      86 |     rows_buffered: int = 0  # Passthrough mode buffered tokens
```

- [ ] Add test to catch mutations on this line

### Line 85 (2 mutants)

```python
      83 |     rows_forked: int = 0
      84 |     rows_coalesced: int = 0
>>>   85 |     rows_expanded: int = 0  # Deaggregation parent tokens
      86 |     rows_buffered: int = 0  # Passthrough mode buffered tokens
      87 |
```

- [ ] Add test to catch mutations on this line

### Line 119

```python
     117 |         self,
     118 |         db: LandscapeDB,
>>>  119 |         *,
     120 |         canonical_version: str = "sha256-rfc8785-v1",
     121 |         checkpoint_manager: "CheckpointManager | None" = None,
```

- [ ] Add test to catch mutations on this line

### Line 151

```python
     149 |         if self._checkpoint_manager is None:
     150 |             return
>>>  151 |
     152 |         self._sequence_number += 1
     153 |
```

- [ ] Add test to catch mutations on this line

### Line 153 (2 mutants)

```python
     151 |
     152 |         self._sequence_number += 1
>>>  153 |
     154 |         should_checkpoint = False
     155 |         if self._checkpoint_settings.frequency == "every_row":
```

- [ ] Add test to catch mutations on this line

### Line 196

```python
     194 |             except Exception as e:
     195 |                 # Log but don't raise - cleanup should be best-effort
>>>  196 |                 logger.warning(
     197 |                     "Transform cleanup failed",
     198 |                     transform=transform.name,
```

- [ ] Add test to catch mutations on this line

### Line 230

```python
     228 |         node_id_to_gate_name: dict[str, str] = {}
     229 |         for seq, transform in enumerate(transforms):
>>>  230 |             if isinstance(transform, BaseGate):
     231 |                 node_id = transform_id_map.get(seq)
     232 |                 if node_id is not None:
```

- [ ] Add test to catch mutations on this line

### Line 231

```python
     229 |         for seq, transform in enumerate(transforms):
     230 |             if isinstance(transform, BaseGate):
>>>  231 |                 node_id = transform_id_map.get(seq)
     232 |                 if node_id is not None:
     233 |                     node_id_to_gate_name[node_id] = transform.name
```

- [ ] Add test to catch mutations on this line

### Line 232

```python
     230 |             if isinstance(transform, BaseGate):
     231 |                 node_id = transform_id_map.get(seq)
>>>  232 |                 if node_id is not None:
     233 |                     node_id_to_gate_name[node_id] = transform.name
     234 |
```

- [ ] Add test to catch mutations on this line

### Line 235

```python
     233 |                     node_id_to_gate_name[node_id] = transform.name
     234 |
>>>  235 |         # Add config gates to the lookup
     236 |         if config_gate_id_map and config_gates:
     237 |             for gate_config in config_gates:
```

- [ ] Add test to catch mutations on this line

### Line 237

```python
     235 |         # Add config gates to the lookup
     236 |         if config_gate_id_map and config_gates:
>>>  237 |             for gate_config in config_gates:
     238 |                 node_id = config_gate_id_map.get(gate_config.name)
     239 |                 if node_id is not None:
```

- [ ] Add test to catch mutations on this line

### Line 238

```python
     236 |         if config_gate_id_map and config_gates:
     237 |             for gate_config in config_gates:
>>>  238 |                 node_id = config_gate_id_map.get(gate_config.name)
     239 |                 if node_id is not None:
     240 |                     node_id_to_gate_name[node_id] = gate_config.name
```

- [ ] Add test to catch mutations on this line

### Line 245

```python
     243 |         for (gate_node_id, route_label), destination in route_resolution_map.items():
     244 |             # "continue" means proceed to next transform, not a sink
>>>  245 |             if destination == "continue":
     246 |                 continue
     247 |
```

- [ ] Add test to catch mutations on this line

### Line 249

```python
     247 |
     248 |             # "fork" means fork to multiple paths, not a sink
>>>  249 |             if destination == "fork":
     250 |                 continue
     251 |
```

- [ ] Add test to catch mutations on this line

### Line 255

```python
     253 |             if destination not in available_sinks:
     254 |                 gate_name = node_id_to_gate_name.get(gate_node_id, gate_node_id)
>>>  255 |                 raise RouteValidationError(
     256 |                     f"Gate '{gate_name}' can route to '{destination}' "
     257 |                     f"(via route label '{route_label}') but no sink named "
```

- [ ] Add test to catch mutations on this line

### Line 256

```python
     254 |                 gate_name = node_id_to_gate_name.get(gate_node_id, gate_node_id)
     255 |                 raise RouteValidationError(
>>>  256 |                     f"Gate '{gate_name}' can route to '{destination}' "
     257 |                     f"(via route label '{route_label}') but no sink named "
     258 |                     f"'{destination}' exists. Available sinks: {sorted(available_sinks)}"
```

- [ ] Add test to catch mutations on this line

### Line 257

```python
     255 |                 raise RouteValidationError(
     256 |                     f"Gate '{gate_name}' can route to '{destination}' "
>>>  257 |                     f"(via route label '{route_label}') but no sink named "
     258 |                     f"'{destination}' exists. Available sinks: {sorted(available_sinks)}"
     259 |                 )
```

- [ ] Add test to catch mutations on this line

### Line 283

```python
     281 |         for transform in transforms:
     282 |             # Only BaseTransform has _on_error; BaseGate uses routing, not error sinks
>>>  283 |             if not isinstance(transform, BaseTransform):
     284 |                 continue
     285 |
```

- [ ] Add test to catch mutations on this line

### Line 290

```python
     288 |
     289 |             if on_error is None:
>>>  290 |                 # No error routing configured - that's fine
     291 |                 continue
     292 |
```

- [ ] Add test to catch mutations on this line

### Line 294

```python
     292 |
     293 |             if on_error == "discard":
>>>  294 |                 # "discard" is a special value, not a sink name
     295 |                 continue
     296 |
```

- [ ] Add test to catch mutations on this line

### Line 299

```python
     297 |             # on_error should reference an existing sink
     298 |             if on_error not in available_sinks:
>>>  299 |                 raise RouteValidationError(
     300 |                     f"Transform '{transform.name}' has on_error='{on_error}' "
     301 |                     f"but no sink named '{on_error}' exists. "
```

- [ ] Add test to catch mutations on this line

### Line 300

```python
     298 |             if on_error not in available_sinks:
     299 |                 raise RouteValidationError(
>>>  300 |                     f"Transform '{transform.name}' has on_error='{on_error}' "
     301 |                     f"but no sink named '{on_error}' exists. "
     302 |                     f"Available sinks: {sorted(available_sinks)}. "
```

- [ ] Add test to catch mutations on this line

### Line 301

```python
     299 |                 raise RouteValidationError(
     300 |                     f"Transform '{transform.name}' has on_error='{on_error}' "
>>>  301 |                     f"but no sink named '{on_error}' exists. "
     302 |                     f"Available sinks: {sorted(available_sinks)}. "
     303 |                     f"Use 'discard' to drop error rows without routing."
```

- [ ] Add test to catch mutations on this line

### Line 302

```python
     300 |                     f"Transform '{transform.name}' has on_error='{on_error}' "
     301 |                     f"but no sink named '{on_error}' exists. "
>>>  302 |                     f"Available sinks: {sorted(available_sinks)}. "
     303 |                     f"Use 'discard' to drop error rows without routing."
     304 |                 )
```

- [ ] Add test to catch mutations on this line

### Line 337

```python
     335 |         if not isinstance(on_validation_failure, str):
     336 |             return
>>>  337 |
     338 |         if on_validation_failure == "discard":
     339 |             # "discard" is a special value, not a sink name
```

- [ ] Add test to catch mutations on this line

### Line 344

```python
     342 |         # on_validation_failure should reference an existing sink
     343 |         if on_validation_failure not in available_sinks:
>>>  344 |             raise RouteValidationError(
     345 |                 f"Source '{source.name}' has on_validation_failure='{on_validation_failure}' "
     346 |                 f"but no sink named '{on_validation_failure}' exists. "
```

- [ ] Add test to catch mutations on this line

### Line 345

```python
     343 |         if on_validation_failure not in available_sinks:
     344 |             raise RouteValidationError(
>>>  345 |                 f"Source '{source.name}' has on_validation_failure='{on_validation_failure}' "
     346 |                 f"but no sink named '{on_validation_failure}' exists. "
     347 |                 f"Available sinks: {sorted(available_sinks)}. "
```

- [ ] Add test to catch mutations on this line

### Line 346

```python
     344 |             raise RouteValidationError(
     345 |                 f"Source '{source.name}' has on_validation_failure='{on_validation_failure}' "
>>>  346 |                 f"but no sink named '{on_validation_failure}' exists. "
     347 |                 f"Available sinks: {sorted(available_sinks)}. "
     348 |                 f"Use 'discard' to drop invalid rows without routing."
```

- [ ] Add test to catch mutations on this line

### Line 347

```python
     345 |                 f"Source '{source.name}' has on_validation_failure='{on_validation_failure}' "
     346 |                 f"but no sink named '{on_validation_failure}' exists. "
>>>  347 |                 f"Available sinks: {sorted(available_sinks)}. "
     348 |                 f"Use 'discard' to drop invalid rows without routing."
     349 |             )
```

- [ ] Add test to catch mutations on this line

### Line 384

```python
     382 |         for seq, transform in enumerate(transforms):
     383 |             if transform.node_id is not None:
>>>  384 |                 # Already has node_id (e.g., aggregation transform) - skip
     385 |                 continue
     386 |             if seq not in transform_id_map:
```

- [ ] Add test to catch mutations on this line

### Line 387

```python
     385 |                 continue
     386 |             if seq not in transform_id_map:
>>>  387 |                 raise ValueError(
     388 |                     f"Transform at sequence {seq} not found in graph. Graph has mappings for sequences: {list(transform_id_map.keys())}"
     389 |                 )
```

- [ ] Add test to catch mutations on this line

### Line 394

```python
     392 |         # Set node_id on sinks
     393 |         for sink_name, sink in sinks.items():
>>>  394 |             if sink_name not in sink_id_map:
     395 |                 raise ValueError(f"Sink '{sink_name}' not found in graph. Available sinks: {list(sink_id_map.keys())}")
     396 |             sink.node_id = sink_id_map[sink_name]
```

- [ ] Add test to catch mutations on this line

### Line 427

```python
     425 |             ValueError: If graph is not provided
     426 |         """
>>>  427 |         if graph is None:
     428 |             raise ValueError("ExecutionGraph is required. Build with ExecutionGraph.from_config(settings)")
     429 |
```

- [ ] Add test to catch mutations on this line

### Line 431

```python
     429 |
     430 |         # Validate schema compatibility
>>>  431 |         # Schemas are required by plugin protocols - access directly
     432 |         source_output = config.source.output_schema
     433 |         transform_inputs = [t.input_schema for t in config.transforms]
```

- [ ] Add test to catch mutations on this line

### Line 443 (2 mutants)

```python
     441 |             sink_inputs=sink_inputs,  # type: ignore[arg-type]
     442 |         )
>>>  443 |         if schema_errors:
     444 |             raise ValueError(f"Pipeline schema incompatibility: {'; '.join(schema_errors)}")
     445 |
```

- [ ] Add test to catch mutations on this line

### Line 453

```python
     451 |             canonical_version=self._canonical_version,
     452 |         )
>>>  453 |
     454 |         run_completed = False
     455 |         try:
```

- [ ] Add test to catch mutations on this line

### Line 470 (2 mutants)

```python
     468 |             # Complete run
     469 |             recorder.complete_run(run.run_id, status="completed")
>>>  470 |             result.status = RunStatus.COMPLETED
     471 |             run_completed = True
     472 |
```

- [ ] Add test to catch mutations on this line

### Line 590

```python
     588 |             # Config gates, aggregations, and coalesce nodes have metadata in graph node, not plugin instances
     589 |             if node_id in config_gate_node_ids:
>>>  590 |                 # Config gates are deterministic (expression evaluation is deterministic)
     591 |                 plugin_version = "1.0.0"
     592 |                 determinism = Determinism.DETERMINISTIC
```

- [ ] Add test to catch mutations on this line

### Line 595 (2 mutants)

```python
     593 |             elif node_id in aggregation_node_ids:
     594 |                 # Aggregations use batch-aware transforms - determinism depends on the transform
>>>  595 |                 # Default to deterministic (statistical operations are typically deterministic)
     596 |                 plugin_version = "1.0.0"
     597 |                 determinism = Determinism.DETERMINISTIC
```

- [ ] Add test to catch mutations on this line

### Line 596

```python
     594 |                 # Aggregations use batch-aware transforms - determinism depends on the transform
     595 |                 # Default to deterministic (statistical operations are typically deterministic)
>>>  596 |                 plugin_version = "1.0.0"
     597 |                 determinism = Determinism.DETERMINISTIC
     598 |             elif node_id in coalesce_node_ids:
```

- [ ] Add test to catch mutations on this line

### Line 599

```python
     597 |                 determinism = Determinism.DETERMINISTIC
     598 |             elif node_id in coalesce_node_ids:
>>>  599 |                 # Coalesce nodes merge tokens from parallel paths - deterministic operation
     600 |                 plugin_version = "1.0.0"
     601 |                 determinism = Determinism.DETERMINISTIC
```

- [ ] Add test to catch mutations on this line

### Line 614

```python
     612 |
     613 |             # Get schema_config from node_info config or default to dynamic
>>>  614 |             # Schema is specified in pipeline config, not plugin attributes
     615 |             schema_dict = node_info.config.get("schema", {"fields": "dynamic"})
     616 |             schema_config = SchemaConfig.from_dict(schema_dict)
```

- [ ] Add test to catch mutations on this line

---

## core/landscape/models.py

**Priority:** P2 — Audit data models
**Survivors:** 36 unique lines (37 total mutants)

### Line 38

```python
      36 |     settings_json: str
      37 |     canonical_version: str
>>>   38 |     status: RunStatus
      39 |     completed_at: datetime | None = None
      40 |     reproducibility_grade: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 39

```python
      37 |     canonical_version: str
      38 |     status: RunStatus
>>>   39 |     completed_at: datetime | None = None
      40 |     reproducibility_grade: str | None = None
      41 |     # Export tracking - separate from run status
```

- [ ] Add test to catch mutations on this line

### Line 41

```python
      39 |     completed_at: datetime | None = None
      40 |     reproducibility_grade: str | None = None
>>>   41 |     # Export tracking - separate from run status
      42 |     export_status: ExportStatus | None = None
      43 |     export_error: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 42

```python
      40 |     reproducibility_grade: str | None = None
      41 |     # Export tracking - separate from run status
>>>   42 |     export_status: ExportStatus | None = None
      43 |     export_error: str | None = None
      44 |     exported_at: datetime | None = None
```

- [ ] Add test to catch mutations on this line

### Line 43

```python
      41 |     # Export tracking - separate from run status
      42 |     export_status: ExportStatus | None = None
>>>   43 |     export_error: str | None = None
      44 |     exported_at: datetime | None = None
      45 |     export_format: str | None = None  # csv, json
```

- [ ] Add test to catch mutations on this line

### Line 44

```python
      42 |     export_status: ExportStatus | None = None
      43 |     export_error: str | None = None
>>>   44 |     exported_at: datetime | None = None
      45 |     export_format: str | None = None  # csv, json
      46 |     export_sink: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 45

```python
      43 |     export_error: str | None = None
      44 |     exported_at: datetime | None = None
>>>   45 |     export_format: str | None = None  # csv, json
      46 |     export_sink: str | None = None
      47 |
```

- [ ] Add test to catch mutations on this line

### Line 61

```python
      59 |     config_hash: str
      60 |     config_json: str
>>>   61 |     registered_at: datetime
      62 |     schema_hash: str | None = None
      63 |     sequence_in_pipeline: int | None = None
```

- [ ] Add test to catch mutations on this line

### Line 62

```python
      60 |     config_json: str
      61 |     registered_at: datetime
>>>   62 |     schema_hash: str | None = None
      63 |     sequence_in_pipeline: int | None = None
      64 |
```

- [ ] Add test to catch mutations on this line

### Line 88

```python
      86 |     row_index: int
      87 |     source_data_hash: str
>>>   88 |     created_at: datetime
      89 |     source_data_ref: str | None = None  # Payload store reference
      90 |
```

- [ ] Add test to catch mutations on this line

### Line 98

```python
      96 |     token_id: str
      97 |     row_id: str
>>>   98 |     created_at: datetime
      99 |     fork_group_id: str | None = None
     100 |     join_group_id: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 99

```python
      97 |     row_id: str
      98 |     created_at: datetime
>>>   99 |     fork_group_id: str | None = None
     100 |     join_group_id: str | None = None
     101 |     expand_group_id: str | None = None  # For deaggregation grouping
```

- [ ] Add test to catch mutations on this line

### Line 100

```python
      98 |     created_at: datetime
      99 |     fork_group_id: str | None = None
>>>  100 |     join_group_id: str | None = None
     101 |     expand_group_id: str | None = None  # For deaggregation grouping
     102 |     branch_name: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 101

```python
      99 |     fork_group_id: str | None = None
     100 |     join_group_id: str | None = None
>>>  101 |     expand_group_id: str | None = None  # For deaggregation grouping
     102 |     branch_name: str | None = None
     103 |     step_in_pipeline: int | None = None  # Step where this token was created (fork/coalesce/expand)
```

- [ ] Add test to catch mutations on this line

### Line 102

```python
     100 |     join_group_id: str | None = None
     101 |     expand_group_id: str | None = None  # For deaggregation grouping
>>>  102 |     branch_name: str | None = None
     103 |     step_in_pipeline: int | None = None  # Step where this token was created (fork/coalesce/expand)
     104 |
```

- [ ] Add test to catch mutations on this line

### Line 137

```python
     135 |     status: Literal[NodeStateStatus.OPEN]
     136 |     input_hash: str
>>>  137 |     started_at: datetime
     138 |     context_before_json: str | None = None
     139 |
```

- [ ] Add test to catch mutations on this line

### Line 164

```python
     162 |     output_hash: str
     163 |     completed_at: datetime
>>>  164 |     duration_ms: float
     165 |     context_before_json: str | None = None
     166 |     context_after_json: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 165

```python
     163 |     completed_at: datetime
     164 |     duration_ms: float
>>>  165 |     context_before_json: str | None = None
     166 |     context_after_json: str | None = None
     167 |
```

- [ ] Add test to catch mutations on this line

### Line 191

```python
     189 |     started_at: datetime
     190 |     completed_at: datetime
>>>  191 |     duration_ms: float
     192 |     error_json: str | None = None
     193 |     output_hash: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 192

```python
     190 |     completed_at: datetime
     191 |     duration_ms: float
>>>  192 |     error_json: str | None = None
     193 |     output_hash: str | None = None
     194 |     context_before_json: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 193

```python
     191 |     duration_ms: float
     192 |     error_json: str | None = None
>>>  193 |     output_hash: str | None = None
     194 |     context_before_json: str | None = None
     195 |     context_after_json: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 194

```python
     192 |     error_json: str | None = None
     193 |     output_hash: str | None = None
>>>  194 |     context_before_json: str | None = None
     195 |     context_after_json: str | None = None
     196 |
```

- [ ] Add test to catch mutations on this line

### Line 198 (2 mutants)

```python
     196 |
     197 |
>>>  198 | # Discriminated union type - use status field to discriminate
     199 | NodeState = NodeStateOpen | NodeStateCompleted | NodeStateFailed
     200 | """Union type for all node states.
```

- [ ] Add test to catch mutations on this line

### Line 222

```python
     220 |     status: str  # success, error
     221 |     request_hash: str
>>>  222 |     created_at: datetime
     223 |     request_ref: str | None = None
     224 |     response_hash: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 223

```python
     221 |     request_hash: str
     222 |     created_at: datetime
>>>  223 |     request_ref: str | None = None
     224 |     response_hash: str | None = None
     225 |     response_ref: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 224

```python
     222 |     created_at: datetime
     223 |     request_ref: str | None = None
>>>  224 |     response_hash: str | None = None
     225 |     response_ref: str | None = None
     226 |     error_json: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 225

```python
     223 |     request_ref: str | None = None
     224 |     response_hash: str | None = None
>>>  225 |     response_ref: str | None = None
     226 |     error_json: str | None = None
     227 |     latency_ms: float | None = None
```

- [ ] Add test to catch mutations on this line

### Line 226

```python
     224 |     response_hash: str | None = None
     225 |     response_ref: str | None = None
>>>  226 |     error_json: str | None = None
     227 |     latency_ms: float | None = None
     228 |
```

- [ ] Add test to catch mutations on this line

### Line 242

```python
     240 |     content_hash: str
     241 |     size_bytes: int
>>>  242 |     created_at: datetime
     243 |     idempotency_key: str | None = None  # For retry deduplication
     244 |
```

- [ ] Add test to catch mutations on this line

### Line 256

```python
     254 |     ordinal: int
     255 |     mode: str  # move, copy
>>>  256 |     created_at: datetime
     257 |     reason_hash: str | None = None
     258 |     reason_ref: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 257

```python
     255 |     mode: str  # move, copy
     256 |     created_at: datetime
>>>  257 |     reason_hash: str | None = None
     258 |     reason_ref: str | None = None
     259 |
```

- [ ] Add test to catch mutations on this line

### Line 270

```python
     268 |     attempt: int
     269 |     status: BatchStatus
>>>  270 |     created_at: datetime
     271 |     aggregation_state_id: str | None = None
     272 |     trigger_reason: str | None = None
```

- [ ] Add test to catch mutations on this line

### Line 271

```python
     269 |     status: BatchStatus
     270 |     created_at: datetime
>>>  271 |     aggregation_state_id: str | None = None
     272 |     trigger_reason: str | None = None
     273 |     trigger_type: str | None = None  # TriggerType enum value
```

- [ ] Add test to catch mutations on this line

### Line 272

```python
     270 |     created_at: datetime
     271 |     aggregation_state_id: str | None = None
>>>  272 |     trigger_reason: str | None = None
     273 |     trigger_type: str | None = None  # TriggerType enum value
     274 |     completed_at: datetime | None = None
```

- [ ] Add test to catch mutations on this line

### Line 273

```python
     271 |     aggregation_state_id: str | None = None
     272 |     trigger_reason: str | None = None
>>>  273 |     trigger_type: str | None = None  # TriggerType enum value
     274 |     completed_at: datetime | None = None
     275 |
```

- [ ] Add test to catch mutations on this line

### Line 308

```python
     306 |     node_id: str
     307 |     sequence_number: int
>>>  308 |     created_at: datetime | None
     309 |     aggregation_state_json: str | None = None
     310 |
```

- [ ] Add test to catch mutations on this line

---

## core/checkpoint/recovery.py

**Priority:** P1 — Pipeline recovery - must be reliable
**Survivors:** 13 unique lines (13 total mutants)

### Line 31

```python
      29 |     """
      30 |
>>>   31 |     can_resume: bool
      32 |     reason: str | None = None
      33 |
```

- [ ] Add test to catch mutations on this line

### Line 35

```python
      33 |
      34 |     def __post_init__(self) -> None:
>>>   35 |         if self.can_resume and self.reason is not None:
      36 |             raise ValueError("can_resume=True should not have a reason")
      37 |         if not self.can_resume and self.reason is None:
```

- [ ] Add test to catch mutations on this line

### Line 37

```python
      35 |         if self.can_resume and self.reason is not None:
      36 |             raise ValueError("can_resume=True should not have a reason")
>>>   37 |         if not self.can_resume and self.reason is None:
      38 |             raise ValueError("can_resume=False must have a reason explaining why")
      39 |
```

- [ ] Add test to catch mutations on this line

### Line 100

```python
      98 |         """
      99 |         run = self._get_run(run_id)
>>>  100 |         if run is None:
     101 |             return ResumeCheck(can_resume=False, reason=f"Run {run_id} not found")
     102 |
```

- [ ] Add test to catch mutations on this line

### Line 103

```python
     101 |             return ResumeCheck(can_resume=False, reason=f"Run {run_id} not found")
     102 |
>>>  103 |         if run.status == RunStatus.COMPLETED:
     104 |             return ResumeCheck(can_resume=False, reason="Run already completed successfully")
     105 |
```

- [ ] Add test to catch mutations on this line

### Line 106

```python
     104 |             return ResumeCheck(can_resume=False, reason="Run already completed successfully")
     105 |
>>>  106 |         if run.status == RunStatus.RUNNING:
     107 |             return ResumeCheck(can_resume=False, reason="Run is still in progress")
     108 |
```

- [ ] Add test to catch mutations on this line

### Line 110

```python
     108 |
     109 |         checkpoint = self._checkpoint_manager.get_latest_checkpoint(run_id)
>>>  110 |         if checkpoint is None:
     111 |             return ResumeCheck(can_resume=False, reason="No checkpoint found for recovery")
     112 |
```

- [ ] Add test to catch mutations on this line

### Line 138

```python
     136 |         if checkpoint is None:
     137 |             return None
>>>  138 |
     139 |         agg_state = None
     140 |         if checkpoint.aggregation_state_json:
```

- [ ] Add test to catch mutations on this line

### Line 186

```python
     184 |                 ).fetchone()
     185 |
>>>  186 |                 if row_result is None:
     187 |                     raise ValueError(f"Row {row_id} not found in database")
     188 |
```

- [ ] Add test to catch mutations on this line

### Line 192

```python
     190 |                 source_data_ref = row_result.source_data_ref
     191 |
>>>  192 |                 if source_data_ref is None:
     193 |                     raise ValueError(f"Row {row_id} has no source_data_ref - cannot resume without payload")
     194 |
```

- [ ] Add test to catch mutations on this line

### Line 199

```python
     197 |                     payload_bytes = payload_store.retrieve(source_data_ref)
     198 |                     row_data = json.loads(payload_bytes.decode("utf-8"))
>>>  199 |                 except KeyError:
     200 |                     raise ValueError(f"Row {row_id} payload has been purged - cannot resume") from None
     201 |
```

- [ ] Add test to catch mutations on this line

### Line 243

```python
     241 |
     242 |             if checkpointed_row_result is None:
>>>  243 |                 raise RuntimeError(
     244 |                     f"Checkpoint references non-existent token: {checkpoint.token_id}. "
     245 |                     "This indicates database corruption or a bug in checkpoint creation."
```

- [ ] Add test to catch mutations on this line

### Line 244

```python
     242 |             if checkpointed_row_result is None:
     243 |                 raise RuntimeError(
>>>  244 |                     f"Checkpoint references non-existent token: {checkpoint.token_id}. "
     245 |                     "This indicates database corruption or a bug in checkpoint creation."
     246 |                 )
```

- [ ] Add test to catch mutations on this line

---

## core/checkpoint/manager.py

**Priority:** P2 — Checkpoint persistence
**Survivors:** 2 unique lines (3 total mutants)

### Line 53 (2 mutants)

```python
      51 |         Returns:
      52 |             The created Checkpoint
>>>   53 |         """
      54 |         checkpoint_id = f"cp-{uuid.uuid4().hex[:12]}"
      55 |         now = datetime.now(UTC)
```

- [ ] Add test to catch mutations on this line

### Line 96

```python
      94 |                 select(checkpoints_table)
      95 |                 .where(checkpoints_table.c.run_id == run_id)
>>>   96 |                 .order_by(desc(checkpoints_table.c.sequence_number))
      97 |                 .limit(1)
      98 |             ).fetchone()
```

- [ ] Add test to catch mutations on this line

---

## core/canonical.py

**Priority:** P2 — Hash integrity
**Survivors:** 1 unique lines (1 total mutants)

### Line 47

```python
      45 |         ValueError: If value contains NaN or Infinity
      46 |     """
>>>   47 |     # Check for NaN/Infinity FIRST (before type coercion)
      48 |     if isinstance(obj, float | np.floating):
      49 |         if math.isnan(obj) or math.isinf(obj):
```

- [ ] Add test to catch mutations on this line

---

## core/landscape/lineage.py

**Priority:** P2 — Lineage queries
**Survivors:** 1 unique lines (1 total mutants)

### Line 58

```python
      56 |     transform_errors: list[TransformErrorRecord] = field(default_factory=list)
      57 |     """Transform errors for this token (from transform processing)."""
>>>   58 |
      59 |     outcome: TokenOutcome | None = None
      60 |     """Terminal outcome for this token (COMPLETED, ROUTED, FAILED, etc.)."""
```

- [ ] Add test to catch mutations on this line

---

## core/landscape/schema.py (Deferred)

**Survivors:** 172

These are SQLAlchemy table definitions. Most are likely equivalent mutants
(changes that don't affect runtime behavior) or require database integration
tests. Review after addressing P1/P2 items.
