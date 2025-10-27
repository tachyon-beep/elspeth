# [TYPE]-[NUMBER]: [Title]

**Priority**: P[0-4] ([CRITICAL|HIGH|MEDIUM|LOW|NICE-TO-HAVE])
**Effort**: [X-Y] hours ([weeks/days] estimate)
**Sprint**: Sprint [N] / Post-[Milestone]
**Status**: [PLANNED|IN PROGRESS|COMPLETE|BLOCKED|CANCELLED]
**Completed**: [Date if complete]
**Depends On**: [List dependencies: VULN-XXX, FEAT-XXX, ADR-XXX, or None]
**Pre-1.0**: [Breaking changes acceptable|Maintain backward compatibility]
**GitHub Issue**: #[issue-number]

**Implementation Note**: [Optional - Alternative approaches, key decisions, or deviations from original plan]

---

## Problem Description / Context

### [VULN-XXX]: [Vulnerability Name] OR [FEAT-XXX]: [Feature Name]

**Finding** / **Problem Statement**:
[Clear description of what's wrong or what needs to be built]

**Impact** / **Motivation**:
- [Bullet point 1]
- [Bullet point 2]
- [Bullet point 3]

**Attack Scenario** (for vulnerabilities):
```[language]
# Code example showing the vulnerability
```

**Use Case** (for features):
```[language]
# Code example showing desired functionality
```

**Related ADRs**: [ADR-XXX], [ADR-YYY]

**Status**: [ADR implemented|ADR documented but not implemented|No ADR]

---

## Current State Analysis

### Existing [Architecture|Implementation]

**What Exists**:
```[language]
# Show current code structure
```

**Problems**:
1. [Problem 1]
2. [Problem 2]
3. [Problem 3]

### What's Missing

1. **[Component 1]** - [Description]
2. **[Component 2]** - [Description]
3. **[Component 3]** - [Description]

### Files Requiring Changes

**Core Framework**:
- `[path/to/file.py]` (NEW|UPDATE) - [What changes]
- `[path/to/file.py]` (NEW|UPDATE) - [What changes]

**[Other Category]** ([N] files to update):
- `[path/to/file.py]`
- `[path/to/file.py]`

**Tests** ([N] new test files):
- `tests/test_[name].py` (NEW)
- `tests/test_[name].py` (UPDATE)

---

## Target Architecture / Design

### Design Overview

```
[ASCII diagram showing target architecture]
```

**Key Design Decisions**:
1. **[Decision 1]**: [Rationale]
2. **[Decision 2]**: [Rationale]
3. **[Decision 3]**: [Rationale]

### API Design (if applicable)

```python
# Show proposed API usage
```

### Security Properties (for security work)

| Threat | Defense Layer | Status |
|--------|--------------|--------|
| **T1: [Threat]** | [Defense mechanism] | [STATUS] |
| **T2: [Threat]** | [Defense mechanism] | [STATUS] |

---

## Design Decisions

### 1. [Major Decision Name]

**Problem**: [What problem this decision addresses]

**Options Considered**:
- **Option A**: [Description] - [Pros/Cons]
- **Option B**: [Description] - [Pros/Cons]
- **Option C**: [Description] - [Pros/Cons]

**Decision**: [Chosen option]

**Rationale**: [Why this was chosen]

### 2. [Error Handling Strategy|Breaking Change Strategy|etc.]

[Similar structure as above]

---

## Implementation Phases (TDD Approach)

### Phase [N.0]: [Phase Name] ([X-Y] hours)

#### Objective
[What this phase accomplishes]

#### Implementation

**Files to Modify**:
```python
# [path/to/file.py]
# Show key code changes
```

**Changes**:
1. [Change 1]
2. [Change 2]
3. [Change 3]

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_[name].py (NEW FILE)
import pytest

def test_[requirement]():
    """[SECURITY|FUNCTIONAL]: [What this test validates]."""
    # Arrange
    [setup code]

    # Act
    [action that should fail]

    # Assert
    with pytest.raises([ErrorType], match="[expected message]"):
        [code that triggers error]
```

**GREEN - Implement Fix**:
```python
# src/[path]/[file].py
# Show implementation that makes test pass
```

**REFACTOR - Improve Code**:
[Describe refactoring steps: extract methods, improve names, add docs, etc.]

#### Migration (if breaking changes)

**Step 1**: [Migration step]
```bash
# Commands to discover affected code
```

**Step 2**: [Migration step]
```[language]
# BEFORE (INVALID after changes)
[old pattern]

# AFTER (VALID)
[new pattern]
```

#### Exit Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] Tests passing: [current]/[current] ([delta] new tests)
- [ ] MyPy clean
- [ ] Ruff clean

#### Commit Plan

**Commit [N]**: [Commit title]
```
[Conventional commit format message]

- [Change 1]
- [Change 2]
- Tests: [old count] → [new count] passing (+[delta] tests)

Files modified:
- [path/to/file.py]
- [path/to/file.py]

[ADR reference, closes issue reference]
```

### Phase [N.1]: [Next Phase]

[Repeat structure above]

---

## Test Strategy

### Unit Tests ([X-Y] tests)

**Coverage Areas**:
- [ ] [Test area 1] ([N] tests)
- [ ] [Test area 2] ([N] tests)
- [ ] [Test area 3] ([N] tests)

**Example Test Cases**:
```python
def test_[scenario]():
    """[What this validates]."""
    # Test implementation
```

### Integration Tests ([X-Y] tests)

**Scenarios**:
- [ ] [Scenario 1]
- [ ] [Scenario 2]
- [ ] [Scenario 3]

### Security Tests (for vulnerabilities, [X-Y] tests)

**Attack Scenarios**:
- [ ] [Attack 1] - [Defense validated]
- [ ] [Attack 2] - [Defense validated]

### Property-Based Tests (if applicable)

**Invariants**:
1. [Invariant 1]
2. [Invariant 2]

```python
from hypothesis import given, strategies as st

@given([strategy])
def test_[property]([parameters]):
    """[Property that must hold]."""
    # Property test implementation
```

---

## Risk Assessment

### High Risks

**Risk 1: [Risk Name]**
- **Impact**: [What happens if this risk materializes]
- **Likelihood**: [High|Medium|Low]
- **Mitigation**: [How to prevent or handle]
- **Rollback**: [How to recover]

**Risk 2: [Risk Name]**
[Similar structure]

### Medium Risks

**Risk 1: [Risk Name]**
- **Impact**: [Impact description]
- **Likelihood**: [High|Medium|Low]
- **Mitigation**: [Prevention/handling]
- **Rollback**: [Recovery approach]

### Low Risks

**Risk 1: [Risk Name]**
- **Impact**: [Minimal impact description]
- **Mitigation**: [Simple prevention]
- **Rollback**: [Quick recovery]

---

## Rollback Plan

### If [Phase/Feature] Causes Issues

**Clean Revert Approach (Pre-1.0)**:
```bash
# Revert Phase [N]
git revert HEAD

# Revert Phase [N-1]
git revert HEAD~1

# Full rollback (all phases)
git revert HEAD~[N]..HEAD

# Verify tests pass
pytest
```

**Feature Flag Approach (Post-1.0)**:
```python
# If feature flags used:
if FEATURE_FLAGS.enable_[feature]:
    [new code path]
else:
    [old code path - fallback]
```

### If [Specific Issue] Occurs

**Symptom**: [What users/developers will see]

**Diagnosis**:
```bash
# Commands to verify the issue
```

**Fix**: [How to resolve without rollback]

---

## Acceptance Criteria

### Functional

- [ ] [Requirement 1]
- [ ] [Requirement 2]
- [ ] [Requirement 3]
- [ ] All phases complete (Phase [N.0] through [N.X])
- [ ] Tests passing: [baseline] → [target] ([delta] new tests)

### Security (for vulnerabilities)

- [ ] [Vulnerability ID] resolved
- [ ] [Attack vector] eliminated
- [ ] Defense-in-depth validated
- [ ] No bypass paths identified

### Code Quality

- [ ] Test coverage ≥[X]% for new code
- [ ] MyPy clean (type safety)
- [ ] Ruff clean (code quality)
- [ ] Documentation complete
- [ ] Breaking changes documented

### Documentation

- [ ] CHANGELOG.md updated
- [ ] ADR updated (if applicable)
- [ ] API documentation complete
- [ ] Migration guide created (if breaking changes)
- [ ] [Related docs] updated

---

## Breaking Changes

### Summary

[Brief description of what breaks and why]

### Migration Guide

**Before**:
```python
# Old usage pattern
```

**After**:
```python
# New usage pattern
```

**Migration Steps**:
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Automated Migration** (if applicable):
```bash
# Script to migrate code
```

---

## Implementation Checklist

### Pre-Implementation

- [ ] ADR reviewed/approved (if applicable)
- [ ] Dependencies satisfied (list from header)
- [ ] Design reviewed by [team/person]
- [ ] Test plan approved
- [ ] Branch created: `feature/[name]` or `fix/[name]`

### During Implementation

- [ ] Phase [N.0] complete
- [ ] Phase [N.1] complete
- [ ] Phase [N.2] complete
- [ ] [etc.]
- [ ] All tests passing after each phase
- [ ] Code review completed (if required)

### Post-Implementation

- [ ] Full test suite passing ([N]/[N] tests)
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] Documentation updated
- [ ] PR created and reviewed
- [ ] Merged to [branch]
- [ ] GitHub issue closed (#[number])
- [ ] Project board updated

---

## Related Work

### Dependencies

- **VULN-XXX**: [Why needed]
- **FEAT-XXX**: [Why needed]
- **ADR-XXX**: [Relationship]

### Blocks

- **VULN-YYY**: [What can't proceed without this]
- **FEAT-YYY**: [What depends on this]

### Related Issues

- #[number] - [Issue title]
- #[number] - [Issue title]

---

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase [N.0] | [X-Y]h | [Z]h | [Variance reason] |
| Phase [N.1] | [X-Y]h | [Z]h | [Variance reason] |
| **Total** | **[X-Y]h** | **[Z]h** | [Overall assessment] |

**Methodology**: [TDD|Refactoring|Standard]
**Skills Used**: [List applicable superpowers skills]

---

## Post-Completion Notes

### What Went Well

- [Success 1]
- [Success 2]
- [Success 3]

### What Could Be Improved

- [Improvement 1]
- [Improvement 2]
- [Improvement 3]

### Lessons Learned

- [Lesson 1]
- [Lesson 2]
- [Lesson 3]

### Follow-Up Work Identified

- [ ] [Task 1] (created as [ISSUE-ID])
- [ ] [Task 2] (created as [ISSUE-ID])

---

🤖 Generated using TEMPLATE.md
**Template Version**: 1.0
**Last Updated**: 2025-10-27

**Note**: This is a placeholder document. When fully migrating to GitHub Projects, key tracking information (status, dependencies, time tracking) will move to issue/project metadata. This document will remain for detailed implementation notes and technical design.
