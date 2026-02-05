# Audit: tests/spikes/test_nodeinfo_typed_config_spikes.py

## Summary
This file contains risk reduction spike tests validating assumptions for a NodeInfo typed config refactor. The tests verify hash stability, schema presence, plugin config access patterns, and JSON-safe serialization.

**Lines:** 532
**Test Classes:** 4 (TestHashStability, TestSchemaPresence, TestPluginConfigAccess, TestJsonSafeConfig)
**Test Methods:** 15

## Verdict: PASS - Well-designed spike tests

The tests are appropriately scoped for their purpose as risk reduction spikes that validate assumptions before implementation.

---

## Detailed Analysis

### 1. Defects
**None identified.**

All tests exercise real behavior and have meaningful assertions. The hash stability tests correctly demonstrate both the problem (unfiltered asdict changes hashes) and the solution (filtered asdict produces stable hashes).

### 2. Overmocking
**None.**

The tests use real implementations:
- Real `canonical_json()` and `stable_hash()` functions
- Real plugin instances (PassThrough, FieldMapper, CSVSource, etc.)
- Real `ExecutionGraph.from_plugin_instances()` factory

This is excellent practice for spike tests that need to validate production behavior.

### 3. Missing Coverage
**Minor gap:**

- **Edge case: Empty config dict** - No test verifies hash stability when all optional fields are None and the dataclass has only required fields.

However, this is acceptable for a spike - the main invariants are tested.

### 4. Tests That Do Nothing
**None.**

All tests have concrete assertions that verify specific invariants:
- Hash equality/inequality assertions
- Field presence/absence assertions
- Type assertions on serialization results

### 5. Inefficiency
**Minor optimization opportunity:**

Lines 425-532 (`TestJsonSafeConfig`) create real plugin instances for each test. This is intentional (comment explains why) but could be consolidated into a single parametrized test.

**Recommendation:** Keep as-is. The explicit test methods make it clear which plugin type is being tested if one fails.

### 6. Structural Issues
**Good structure:**

- Clear section headers with `# =====` delimiters
- Each test class has a focused purpose documented in docstrings
- Test names describe what's being validated
- No pytest class discovery issues (all classes prefixed with `Test`)

---

## Notable Patterns (Positive)

### Production Path Testing
Lines 265-328 use `ExecutionGraph.from_plugin_instances()` - the production factory method - rather than manually constructing graphs. This follows the CLAUDE.md guidance on test path integrity.

### Mock vs Real Dataclasses
Lines 27-57 define `MockGateNodeConfig`, `MockTransformNodeConfig`, and `MockCoalesceNodeConfig`. These are test doubles that mirror production structures, not mocks that hide behavior. They enable testing the `config_to_dict_filtered()` logic in isolation.

### Intent Documentation
Each test class has a docstring explaining the invariant being validated and why it matters. This is excellent for spike tests that may be referenced during main implementation.

---

## Recommendations

1. **Consider promoting to regression tests** - These spikes validate important invariants. Consider adding them to the main test suite after the refactor is complete.

2. **Add parametrization for plugin configs** - Lines 425-512 test 3 source types, 3 transform types, and 2 sink types separately. Could be parametrized but current form is acceptable.

---

## Test Quality Score: 9/10

Well-designed spike tests that validate assumptions correctly with real implementations. Minor deduction for potential consolidation opportunity that isn't worth the complexity.
