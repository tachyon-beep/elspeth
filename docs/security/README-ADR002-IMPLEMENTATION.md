# ADR-002 Implementation Guide - START HERE

**Status**: Ready for Implementation (after PR #11 merge)
**Estimated Effort**: 4-6 hours
**Priority**: HIGH (Certification Blocker)

---

## Quick Summary

**Problem**: ADR-002 (accepted 2025-10-23) requires two-layer security enforcement:
1. ✅ **Plugin-level** - Child plugins can't downgrade parent security levels (DONE - 9 tests passing)
2. ❌ **Suite-level** - Orchestrator operates at minimum clearance, high-security components refuse low-clearance envelopes (NOT IMPLEMENTED)

**Solution**: Add "minimum clearance envelope" model to `suite_runner.py` - orchestrator computes operating level, validates ALL components before data retrieval, with runtime failsafes in plugins.

---

## Documents in This Directory

### 1. `adr-002-implementation-gap.md` (MAIN SPEC)
**Purpose**: Complete implementation specification
**Contents**:
- Full gap analysis (what's missing)
- Complete code for 3 helper methods
- 5 integration tests with certification documentation
- Integration points in suite_runner.py
- Risk assessment and effort estimates

**Read first**: Yes - this is the comprehensive spec

### 2. `adr-002-orchestrator-security-model.md` (CLARIFICATION)
**Purpose**: Clarifies the correct "minimum clearance envelope" model
**Contents**:
- How the model actually works (not "datasource blocks sink")
- Key principles: orchestrator operates at minimum, ALL components validate
- Defense in depth: start-time (PRIMARY) + runtime (FAILSAFE)
- Clear examples and test scenarios

**Read second**: Yes - corrects initial misunderstanding in main spec

**KEY INSIGHT FROM THIS DOC**:
- Orchestrator asks all signed plugins for security levels
- Orchestrator operates at MINIMUM level (clearance envelope)
- ALL components validate they can operate at that level
- Job fails to START if any component requires higher
- Runtime validation is failsafe: "what if someone tricks orchestrator?"

---

## The Correct Mental Model

```
┌─────────────────────────────────────────────────────┐
│ Job Start: Orchestrator Asks All Plugins           │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │ Plugin Responses:      │
            │ - Datasource: SECRET   │
            │ - LLM: SECRET          │
            │ - Sink1: SECRET        │
            │ - Sink2: UNOFFICIAL    │ ← One low-security component
            └────────────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │ Orchestrator Computes: │
            │ Operating Level = min()│
            │ = UNOFFICIAL           │ ← Clearance envelope at minimum
            └────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│ Start-Time Validation (MUST BLOCK):                │
│ - Datasource: "I need SECRET, you're UNOFFICIAL" ❌│
│ - LLM: "I need SECRET, you're UNOFFICIAL" ❌       │
│ - Sink1: "I need SECRET, you're UNOFFICIAL" ❌     │
│ - Sink2: "I need UNOFFICIAL, you're UNOFFICIAL" ✅ │
│                                                     │
│ RESULT: Job FAILS TO START (before data retrieval) │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │ If job somehow starts: │
            │ Runtime Validation     │
            │ (Defense in Depth)     │
            │                        │
            │ Each plugin validates  │
            │ before handling data   │
            └────────────────────────┘
```

---

## Implementation Checklist

### Phase 1: Add 3 Helper Methods to `suite_runner.py` (2 hours)

1. `_collect_plugin_security_levels()` - Ask all signed plugins for levels
2. `_compute_orchestrator_operating_level()` - Compute min(levels)
3. `_validate_components_at_operating_level()` - Fail-fast if any requires > operating level

**Code location**: After line 605 (end of existing helper methods section)
**Full implementation**: See `adr-002-implementation-gap.md` Method 1, 2, 3

### Phase 2: Integrate into `run()` Method (1 hour)

**Location**: After line 310, before middleware notification

```python
# Collect levels from all signed plugins
plugin_levels = self._collect_plugin_security_levels(suite, defaults, sink_factory)

# Orchestrator operates at minimum
operating_level = self._compute_orchestrator_operating_level(plugin_levels)

# Fail-fast: validate ALL components can operate at that level
self._validate_components_at_operating_level(plugin_levels, operating_level)

# Set in context for runtime validation (defense in depth)
ctx.orchestrator_operating_level = operating_level
```

### Phase 3: Add Integration Tests (1.5 hours)

**File**: Create `tests/test_suite_runner_adr002_security.py`

**5 required tests**:
1. `test_adr002_fail_fast_secret_datasource_unofficial_sink()` - CRITICAL certification test
2. `test_adr002_pass_matching_security_levels()` - Happy path
3. `test_adr002_pass_security_upgrade_in_pipeline()` - Upgrades allowed
4. `test_adr002_fail_fast_protected_datasource_official_sink()` - Another downgrade scenario
5. `test_adr002_multiple_experiments_minimum_level_enforced()` - Multi-experiment validation

**Full test code**: See `adr-002-implementation-gap.md` Phase 3

### Phase 4: Add Runtime Validation to Plugins (30 min)

**Example for datasources**:
```python
def get_data(self, context):
    # Runtime failsafe (should NEVER trigger if start-time works)
    orch_level = getattr(context, 'orchestrator_operating_level', None)
    if orch_level and SecurityLevel.from_string(orch_level) < self.security_level:
        raise SecurityError(
            f"RUNTIME FAILSAFE: Datasource requires {self.security_level}, "
            f"orchestrator at {orch_level}. Refusing to hand over data."
        )
    return self._retrieve_data()
```

**Repeat for**: Datasources, Sinks, LLM clients, Middlewares

### Phase 5: Validation (1 hour)

- [ ] All 39 existing suite_runner tests pass
- [ ] All 5 new ADR-002 tests pass
- [ ] Performance check: Security validation < 10ms
- [ ] Update ADR-002.md to mark as "Implemented"

---

## Success Criteria

**Minimum Viable**:
1. ✅ 3 helper methods implemented
2. ✅ Integrated into `run()` before middleware notification
3. ✅ 5 integration tests passing
4. ✅ All existing tests still pass

**Full Compliance**:
5. ✅ Runtime validation added to all plugin types
6. ✅ Certification documentation on tests (matching PR #11 style)
7. ✅ Error messages reference ADR-002
8. ✅ ADR-002 marked "Implemented" in architecture docs

---

## Key Design Decisions

### 1. Clearance Envelope Model
- Orchestrator operates at MINIMUM security level
- High-security components refuse to participate in low-clearance envelopes
- NOT "datasource blocks low sink" - it's "ALL components validate against operating level"

### 2. Defense in Depth
- **Start-time** (PRIMARY): Fail-fast before data retrieval - MUST catch all misconfigs
- **Runtime** (FAILSAFE): Each plugin validates when handling data - protects if orchestrator tricked

### 3. ALL Components Validate
- Not just datasource
- Datasources, LLM clients, sinks, middlewares ALL validate
- Any component requiring > operating level causes job to fail at start

### 4. Cryptographic Trust Model
- Plugins are cryptographically signed
- Orchestrator trusts their security level declarations
- Signed plugins can't lie about their requirements

---

## Error Messages

### Start-Time (Normal Path)
```
SecurityError: Component 'datasource' requires SECRET but orchestrator
operating at UNOFFICIAL. Job cannot start - remove low-security component
or create separate pipeline. ADR-002 fail-fast enforcement.
```

### Runtime (Failsafe - Should Never Happen)
```
SecurityError: RUNTIME FAILSAFE: Datasource requires SECRET but orchestrator
operating at UNOFFICIAL. Refusing to hand over data. This should have been
caught at start-time - possible security bypass attempt.
ADR-002 defense-in-depth enforcement.
```

---

## What Changed from Initial Understanding

| Initial (WRONG) | Corrected |
|----------------|-----------|
| "Datasource validates pipeline has low sink" | "Orchestrator operates at minimum, ALL components validate" |
| "Only datasource needs validation" | "ALL high-security components refuse low envelopes" |
| Single validation point | Start-time (PRIMARY) + runtime (FAILSAFE) |
| Datasource-centric | Orchestrator clearance envelope |

**Why this matters**: The reviewer's feedback helped identify that ADR-002 requires a specific "minimum clearance envelope" model, not just "prevent datasource → low sink" validation.

---

## Next Steps

1. **Merge PR #11** (complexity reduction refactoring - 39/39 tests passing)
2. **Create ADR-002 implementation ticket** (reference this README)
3. **Follow checklist above** (Phases 1-5, ~4-6 hours total)
4. **Submit PR** with all 5 success criteria met
5. **Update ADR-002** to mark as "Implemented"

---

## Questions?

- **"Why 3 methods instead of 1?"** - Separation of concerns: collect vs compute vs validate
- **"Why runtime validation if start-time MUST block?"** - Defense in depth failsafe if orchestrator tricked
- **"Why validate ALL components?"** - Clearance envelope model: ANY component > operating level fails
- **"What's the user's operational context?"** - Batch/certification deployment, locked dev→prod, slow cert cycles

---

**Document Status**: Ready for implementation
**Next Action**: Merge PR #11, then implement following this guide
