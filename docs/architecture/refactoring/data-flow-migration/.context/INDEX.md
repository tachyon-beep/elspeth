# Context Index - Quick Navigation

**Use this index to find what you need after memory compaction**

---

## Start Here

1. **[SESSION_STATE.md](SESSION_STATE.md)** - Complete session state
   - What we've accomplished
   - What needs to happen next
   - Current phase: Risk Reduction
   - All gates and success criteria

2. **[ARCHITECTURAL_PRINCIPLES.md](ARCHITECTURAL_PRINCIPLES.md)** - Why we're doing this
   - Core insight: data flow orchestration
   - The car analogy (engine vs components)
   - Key architectural decisions
   - User quotes and rationale

3. **[CODE_PATTERNS.md](CODE_PATTERNS.md)** - Technical reference
   - Current registry structure (18 files)
   - Code patterns (security, validation, etc.)
   - File movement map
   - Useful commands

4. **[RISK_REDUCTION_CHECKLIST.md](RISK_REDUCTION_CHECKLIST.md)** - Track progress
   - 6 activities with detailed checklists
   - All gates that must pass
   - Fill in as you work

---

## Quick Reference

### Current Status
- **Phase**: Risk Reduction (Week 1)
- **Duration**: 8-12 hours
- **Blocked**: Migration cannot start until ALL gates pass
- **Tests**: 545 passing, 0 mypy errors, ruff clean

### Critical Files Modified
- `src/elspeth/core/controls/registry.py:188-191` - Fixed module-level properties (P0)
- `src/elspeth/core/registry/plugin_helpers.py:197-205` - Fixed silent default (P0 security)
- Multiple mypy fixes (0 errors now)

### What to Do Now
1. Start Activity 1: Silent Default Audit (2-3 hours)
2. Then Activity 2: Test Coverage Audit (2-3 hours)
3. Then Activities 3-6 (4-7 hours)
4. Verify ALL gates pass
5. ONLY THEN proceed to migration

---

## File Guide

### Session Context
- **SESSION_STATE.md** - Complete state, accomplished tasks, next steps
- **ARCHITECTURAL_PRINCIPLES.md** - Core insights, decisions, rationale
- **CODE_PATTERNS.md** - Technical details, patterns, commands
- **RISK_REDUCTION_CHECKLIST.md** - Track progress through activities

### Project Documents (parent directory)
- **README.md** - Project overview, status, timeline
- **RISK_REDUCTION_PLAN.md** - Detailed risk mitigation plan
- **ARCHITECTURE_EVOLUTION.md** - Journey through 4 design stages
- **PLUGIN_SYSTEM_DATA_FLOW.md** - Target architecture spec
- **MIGRATION_TO_DATA_FLOW.md** - 5-phase implementation guide
- **CONFIGURATION_ATTRIBUTABILITY.md** - Config snapshot design
- **PLUGIN_SYSTEM_ANALYSIS.md** - Initial analysis (historical)
- **PLUGIN_SYSTEM_REVISED.md** - Intermediate design (historical)

---

## Key Commands

### Risk Reduction Activities

**Activity 1: Silent Default Audit**
```bash
# Search for defaults
rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/ > silent_defaults_audit.txt
rg "\|\|\s*['\"]" src/elspeth/ >> silent_defaults_audit.txt
rg "def create_.*\(.*=.*\):" src/elspeth/ >> silent_defaults_audit.txt
```

**Activity 2: Test Coverage**
```bash
# Generate coverage report
python -m pytest --cov=elspeth --cov-report=html --cov-report=term-missing --cov-report=json

# Run all tests
python -m pytest
```

**Activity 3: Import Mapping**
```bash
# Map registry imports
rg "from elspeth\.core\.registry" src/ tests/ > registry_imports.txt
rg "from elspeth\.core\.datasource_registry" src/ tests/ >> registry_imports.txt
# ... (see CODE_PATTERNS.md for full list)
```

**Activity 4: Performance Baseline**
```bash
# Time execution
time python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 100

# Profile
python -m cProfile -o profile.prof -m elspeth.cli ...
```

**Activity 5: Config Audit**
```bash
# Find configs
find . -name "*.yaml" -o -name "*.yml" | grep -v ".venv" > configs_inventory.txt

# Find plugin references
rg "plugin:\s*" config/ tests/ >> plugin_references.txt
```

### Standard Commands
```bash
# Test
python -m pytest
make sample-suite

# Quality
.venv/bin/python -m mypy src/elspeth
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format src tests
```

---

## Architecture Summary

### Current (LLM-Centric)
```
plugins/
├── datasources/  # 3 files
├── llms/         # 6 files (LLM special)
├── outputs/      # 12 files
├── experiments/  # 5 files
└── utilities/    # 1 file

Registries: 18 files
```

### Target (Data Flow)
```
plugins/
├── orchestrators/         # Engines (topology)
│   └── experiment/
└── nodes/                 # Components (transformations)
    ├── sources/
    ├── sinks/
    ├── transforms/
    │   ├── llm/          # Just ONE transform type
    │   ├── text/
    │   ├── numeric/
    │   └── structural/
    ├── aggregators/
    └── utilities/

Registries: 7 files (61% reduction)
```

---

## Core Principles (Remember These)

1. **Orchestrators define topology** (how data flows) = engine
2. **Nodes define transformations** (what happens) = components
3. **LLM is just another transform** (not special)
4. **No silent defaults** (security + audit requirement)
5. **Config must be complete** (attributability requirement)
6. **Backward compatibility essential** (shims required)

---

## Success Gates (MUST PASS)

### Critical
- [ ] Silent default audit complete
- [ ] Zero P0/P1 silent defaults
- [ ] Test coverage >85%
- [ ] All 545+ tests passing
- [ ] Characterization tests for all 18 registries

### High
- [ ] 5+ end-to-end smoke tests
- [ ] Import chain map complete
- [ ] Backward compat shims designed

### Medium
- [ ] Performance baseline established
- [ ] Config compatibility layer designed
- [ ] Migration checklist created
- [ ] Rollback procedures documented

**All must pass before migration starts**

---

## Timeline

**Week 1: Risk Reduction (8-12 hours)** ← YOU ARE HERE
- Activity 1: Silent defaults (2-3h)
- Activity 2: Test coverage (2-3h)
- Activity 3: Import mapping (2-3h)
- Activity 4: Performance (1-2h)
- Activity 5: Config audit (1-2h)
- Activity 6: Migration safety (2-3h)

**Week 2: Migration (12-17 hours)** ← BLOCKED
- Phase 1: Orchestration (3-4h)
- Phase 2: Nodes (3-4h)
- Phase 3: Security (2-3h)
- Phase 4: Protocols (2-3h)
- Phase 5: Docs/tests (2-3h)

**Total: 20-29 hours**

---

## If You Get Lost

1. **Read SESSION_STATE.md** - know what's been done
2. **Check RISK_REDUCTION_CHECKLIST.md** - see what's next
3. **Review ARCHITECTURAL_PRINCIPLES.md** - understand why
4. **Consult CODE_PATTERNS.md** - find technical details

---

## Key User Insights (Direct Quotes)

> "llm connection is a **function** that any job should be able to do... the core feature is **pumping data between nodes**, the LLM can be one of those nodes"

> "every plugin must be fully specified each time or it won't run"

> "all the configuration for a particular orchestration run has to be colocated for attributability"

> "think of separating the engine from the wheels and steering wheel and fuel tank"

---

## Emergency Procedures

**If something breaks**:
1. Run: `python -m pytest` - should be 545+ passing
2. Run: `make sample-suite` - should complete
3. Check: `git status` - see what changed
4. Rollback: `git reset --hard HEAD` if needed

**If uncertain**:
1. Pause and review context files
2. Check gates in RISK_REDUCTION_CHECKLIST.md
3. Don't proceed until all gates pass

**Remember**: Risk reduction is NOT optional. It prevents 20+ hours of debugging later.
