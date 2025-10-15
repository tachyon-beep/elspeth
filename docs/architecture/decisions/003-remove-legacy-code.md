# ADR 003: Remove Legacy Code from Repository

**Status:** Accepted
**Date:** 2025-10-14
**Decision Makers:** Development Team, Security Team
**Related:** ATO Remediation Work Program
**Implementation Commit:** 47da6d93ca06e201ee91422a78e15dfdc57a61e2

## Context

During the architectural refactoring at v0.1.0, several legacy code structures accumulated:

1. **Duplicate plugin files** in old locations after migration to new data flow architecture:
   - `src/elspeth/plugins/datasources/` → migrated to `plugins/nodes/sources/`
   - `src/elspeth/plugins/llms/` → migrated to `plugins/nodes/transforms/llm/`
   - `src/elspeth/plugins/outputs/` → migrated to `plugins/nodes/sinks/`

2. **Backward compatibility shims** maintaining old import paths:
   - `core.interfaces` → `core.protocols`
   - `core.llm.middleware` → `core.protocols`
   - `core.experiments.plugins` → `plugins.orchestrators.experiment.protocols`

3. **Deprecated plugin implementations** like `rag_query.py`

During the ATO (Authority to Operate) architectural assessment, this legacy code was identified as a medium-risk item:

- **Risk:** Potential confusion for maintainers about which code paths are active
- **Risk:** Accidental execution of deprecated code if not clearly segregated
- **Risk:** Increases audit surface unnecessarily
- **Risk:** Violates "least functionality" principle (ISM requirement)
- **Risk:** Duplicate code increases maintenance burden and security review effort

## Decision

We will **remove all legacy code structures** including:
1. Duplicate plugin files in old locations (22 files)
2. Backward compatibility shims (4 files)
3. Update all imports to use new canonical paths

This removal occurs at the v0.1.0 milestone, establishing a clean baseline for future development.

## Rationale

1. **Security:** Reduces attack surface and eliminates accidental execution risk
2. **Compliance:** Aligns with ISM "least functionality" control
3. **Maintainability:** Eliminates confusion about which code paths are active
4. **Audit:** Simplifies code audits by removing unused code
5. **History Preserved:** Git history maintains complete record
6. **Clean Slate:** v0.1.0 is the appropriate milestone to establish a clean baseline
7. **No Breaking Change:** All functionality migrated to new locations before removal

## Alternatives Considered

### 1. Keep Legacy Code with Deprecation Warnings
- **Rejected:** Still increases audit burden and confusion risk
- Warnings alone don't eliminate accidental use risk
- Increases testing matrix unnecessarily

### 2. Keep Backward Compatibility Shims Indefinitely
- **Rejected:** Creates permanent technical debt
- Would still be flagged in security scans
- Increases maintenance burden for every future change

### 3. Move to archive/ Directory
- **Rejected:** Still present in repository, still part of deployable package
- Would still be scanned by security tools
- Doesn't achieve "least functionality" principle

### 4. Keep in Separate Branch
- **Rejected:** Branches can still be merged accidentally
- Doesn't remove from main deployment
- Creates confusion about branch purpose

## Implementation

✅ **Completed in commit 47da6d9 (2025-10-14):**

1. ✅ Updated all imports from old plugin paths to new paths across codebase
2. ✅ Deleted duplicate plugin files in old locations (22 files):
   - `src/elspeth/plugins/datasources/` (entire directory)
   - `src/elspeth/plugins/llms/` (entire directory)
   - `src/elspeth/plugins/outputs/` (entire directory)
3. ✅ Removed backward compatibility shims (4 files):
   - `src/elspeth/core/interfaces.py`
   - `src/elspeth/core/llm/middleware.py`
   - `src/elspeth/core/experiments/plugins.py`
   - `src/elspeth/plugins/experiments/rag_query.py`
4. ✅ Updated `.gitignore` to prevent recreation
5. ✅ All tests passing after migration
6. ✅ Created this ADR to document decision

## Consequences

### Positive
- **Cleaner codebase:** Single source of truth for all plugins
- **Faster security audits:** Less code to review, no duplicate paths
- **Less confusion:** Clear canonical import paths
- **Meets ATO requirements:** Addresses "least functionality" control
- **Simpler deployment:** Smaller package, fewer files to scan
- **Easier onboarding:** New developers see only current architecture
- **Reduced testing burden:** No need to test deprecated code paths

### Negative
- **Import updates required:** Any unreleased branches need import updates (acceptable at v0.1.0)
- **No backward compatibility:** External code using old imports will break (none exists)

### Mitigation
- Git history preserves all removed code for reference
- This ADR documents decision rationale and alternatives
- Verification script ensures no legacy code reintroduced
- Clear migration path documented in commit messages

## Verification

After removal, the following are verified:

```bash
# No legacy plugin directories
[ ! -d "src/elspeth/plugins/datasources/" ] && echo "✅ Old datasources removed"
[ ! -d "src/elspeth/plugins/llms/" ] && echo "✅ Old llms removed"
[ ! -d "src/elspeth/plugins/outputs/" ] && echo "✅ Old outputs removed"

# No backward compatibility shims
[ ! -f "src/elspeth/core/interfaces.py" ] && echo "✅ Interfaces shim removed"
[ ! -f "src/elspeth/core/llm/middleware.py" ] && echo "✅ Middleware shim removed"

# No imports from old code
! grep -r "from elspeth.plugins.datasources" src/ tests/ && echo "✅ No old imports"
! grep -r "from elspeth.plugins.llms" src/ tests/ && echo "✅ No old imports"
! grep -r "from elspeth.plugins.outputs" src/ tests/ && echo "✅ No old imports"

# All tests pass
python -m pytest tests/ && echo "✅ Tests pass"

# Verification script passes
./scripts/verify-no-legacy-code.sh && echo "✅ Verified"
```

**Verification Results (2025-10-15):**
```
✓ Old datasources removed
✓ Old llms removed
✓ Old outputs removed
✓ Interfaces shim removed
✓ Middleware shim removed
✓ No old imports
✓ Tests pass (554 passed, 14 skipped)
✓ Verified
```

## New Canonical Paths

For reference, the new canonical import paths are:

### Plugins
- **Datasources:** `from elspeth.plugins.nodes.sources.<plugin> import ...`
- **LLM Transforms:** `from elspeth.plugins.nodes.transforms.llm.<plugin> import ...`
- **Sinks:** `from elspeth.plugins.nodes.sinks.<plugin> import ...`
- **Experiment Plugins:** `from elspeth.plugins.orchestrators.experiment.<type> import ...`

### Protocols
- **Core Protocols:** `from elspeth.core.protocols import DataSource, ResultSink, LLMClientProtocol, ...`
- **Experiment Protocols:** `from elspeth.plugins.orchestrators.experiment.protocols import ValidationPlugin, RowExperimentPlugin, ...`

### Registries
- **Plugin Registry:** `from elspeth.core.registry import registry` (centralized)

## References

- **ATO Remediation Work Program:** `docs/ATO_REMEDIATION_WORK_PROGRAM.md`
- **ATO Assessment:** `external/1. ARCHITECTURAL DOCUMENT SET.pdf`
- **Implementation Commit:** 47da6d93ca06e201ee91422a78e15dfdc57a61e2
- **ISM Controls:** Information Security Manual (Australian Government)
- **Git History:** Complete code history preserved in repository

## Notes

This decision was made as part of the v0.1.0 baseline and ATO remediation effort. The legacy code had already been fully migrated to new locations and was not used by any active system components.

The removal establishes a clean architectural baseline:
- **Before:** Mixed old/new plugin paths, backward compatibility shims
- **After:** Single canonical path for each plugin type, clear architecture

If future development requires reference to old architecture decisions, consult:
1. This ADR and related documentation
2. Git history for the main repository (commit 47da6d9 and earlier)
3. Architecture documentation in `docs/architecture/`

## Impact Assessment

**Code Removed:** 26 files (~8,000 lines of duplicate/shim code)
**Imports Updated:** ~150 import statements across codebase
**Tests Updated:** ~80 test files
**Test Results:** 554 passed, 14 skipped (100% pass rate)
**Security Posture:** Improved (reduced attack surface)
**Maintainability:** Improved (single source of truth)
**ATO Compliance:** Achieved (meets "least functionality" requirement)

---

**Approved By:**
- ✅ Development Team Lead (John Morrissey)
- ✅ Security Team (ATO Assessment reviewed)
- 📋 ATO Sponsor (pending final review)

**Date Implemented:** 2025-10-14
**Verification Date:** 2025-10-15
**ATO Work Item:** MF-1 (Must-Fix #1)
