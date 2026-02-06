# Test Audit: tests/engine/test_orchestrator_contracts.py

## Metadata
- **Lines:** 732
- **Tests:** 8 (in 2 test classes)
- **Audit:** PASS

## Summary

Tests for orchestrator schema contract recording and secret resolution recording in the audit trail. Verifies that source contracts are properly recorded to the runs table, source nodes receive output contracts, handles edge cases (no contract, empty pipeline, quarantined first row), and transform schema evolution is tracked. All tests use the production graph building helper.

## Findings

### Production Code Path (PASS)

All tests use `build_production_graph(config, default_sink="default")` which internally uses `ExecutionGraph.from_plugin_instances()`:

```python
graph = build_production_graph(config, default_sink="default")
orchestrator = Orchestrator(db)
result = orchestrator.run(config, graph=graph, payload_store=payload_store)
```

### Test Class Organization

**TestOrchestratorContractRecording** (8 tests):
1. `test_source_contract_recorded_after_first_row` - Basic contract recording
2. `test_source_node_receives_output_contract` - Node-level contract recording
3. `test_no_contract_when_source_returns_none` - Handles None contract
4. `test_contract_recorded_with_empty_pipeline` - Zero rows edge case
5. `test_contract_recorded_after_first_valid_row_not_first_iteration` - Bug fix test for quarantined first row
6. `test_transform_schema_evolution_updates_contract` - Transform adds fields

**TestOrchestratorSecretResolutions** (2 tests):
1. `test_secret_resolutions_recorded_when_provided` - Verifies secret audit trail
2. `test_no_secret_resolutions_when_not_provided` - Handles None case

### Bug Fix Coverage

Good test for the "mwwo" bug fix (line 350-462):
```python
def test_contract_recorded_after_first_valid_row_not_first_iteration(self, payload_store) -> None:
    """Contract recorded after first VALID row, not first iteration.

    BUG FIX: mwwo - Run schema contract tied to first iteration, not first valid row
    """
```

This ensures the contract is recorded after the first successful row, not the first iteration (which might be quarantined).

### Schema Evolution Test

The `test_transform_schema_evolution_updates_contract` test properly verifies that transforms adding fields have their evolved output contract recorded (lines 464-586).

### Secret Resolution Testing

Comprehensive secret resolution testing with:
- Fingerprint verification using `secret_fingerprint()` function
- Environment variable setup via `monkeypatch`
- Database verification of recorded values

### Minor Code Duplication

Each test defines its own `ContractSource`, `SimpleSource`, and `CollectSink` classes inline. However, these are relatively small and the inline definitions make each test self-contained and readable.

### Proper Database Assertions

All tests verify database state directly via SQLAlchemy:
```python
with db.engine.connect() as conn:
    run_row = conn.execute(select(runs_table).where(runs_table.c.run_id == result.run_id)).fetchone()
    assert run_row is not None
    assert run_row.schema_contract_json is not None
```

This verifies the actual audit trail, not just in-memory state.

## Verdict

**PASS** - Well-structured test file with comprehensive coverage of contract recording scenarios. All tests use production code paths, include proper database verification, and cover important edge cases including bug fix regressions. No issues found.
