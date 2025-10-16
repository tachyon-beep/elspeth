# ATO Remediation - Quick Start Guide

This guide will help you get started with the ATO remediation work program.

## 📋 Prerequisites

- [ ] Read the full work program: `docs/ATO_REMEDIATION_WORK_PROGRAM.md`
- [ ] Ensure development environment is set up: `make bootstrap`
- [ ] All tests currently passing: `python -m pytest tests/`
- [ ] Familiarize yourself with ATO assessment: `external/1. ARCHITECTURAL DOCUMENT SET.pdf`

## 🚀 Getting Started - First Day

### Step 1: Set Up Your Workspace (15 minutes)

```bash
# Navigate to project
cd /home/john/elspeth

# Ensure you're on the right branch (or create a new one for ATO work)
git checkout -b ato-remediation-2025

# Run daily verification to establish baseline
./scripts/daily-verification.sh

# If it passes, you're ready to go!
```

### Step 2: Start with MF-1 - Remove Legacy Code (2-4 hours)

This is the highest-priority, lowest-risk task. Perfect to start with!

#### 2.1: Verify No Active References (30 minutes)

```bash
# Run the verification script
./scripts/verify-no-legacy-code.sh

# Search for any imports
grep -r "from old\." src/ tests/
grep -r "import old\." src/ tests/

# Search for dmp namespace (legacy)
grep -r "from dmp\." src/ tests/
grep -r "import dmp\." src/ tests/

# If you find ANY matches, document them before proceeding
# Create a file: docs/ATO_LEGACY_REFERENCES_FOUND.md
```

**Expected Result:** Zero matches (code should be clean)

#### 2.2: Archive the Legacy Code (15 minutes)

```bash
# Create archive directory
mkdir -p ../elspeth-archive/legacy-code-2025-10-15

# Copy the old/ directory
cp -r old/ ../elspeth-archive/legacy-code-2025-10-15/

# Create archive README
cat > ../elspeth-archive/legacy-code-2025-10-15/README.md << 'EOF'
# Elspeth Legacy Code Archive

**Date Archived:** 2025-10-15
**Reason:** ATO remediation - removing unused legacy code
**Original Location:** `old/` directory in main repository
**Commit Before Removal:** $(git rev-parse HEAD)

## Contents

This archive contains the legacy codebase that used the 'dmp' module namespace.
This code represents the pre-refactoring architecture and is no longer used by
the active system.

## Important

**DO NOT reintroduce this code into the active codebase.**

This code is preserved solely for historical reference. If you need to reference
old architecture decisions, consult this archive, but all new development should
use the current architecture documented in `docs/architecture/`.

## Git History

The complete git history is preserved in the main repository. To view the state
of this code when it was active:

```bash
git checkout <commit-hash>
```

Where <commit-hash> is the commit referenced above.
EOF

# Verify the archive
ls -la ../elspeth-archive/legacy-code-2025-10-15/
```

#### 2.3: Remove from Repository (10 minutes)

```bash
# IMPORTANT: Make sure you've archived first! (Step 2.2 above)

# Remove the directory from git
git rm -r old/

# Already done: .gitignore updated to prevent recreation

# Verify it's gone
ls -la old/ 2>&1  # Should show "No such file or directory"

# Check git status
git status
# Should show old/ files as deleted
```

#### 2.4: Create ADR (1 hour)

```bash
# Create the Architectural Decision Record
cat > docs/architecture/decisions/003-remove-legacy-code.md << 'EOF'
# ADR 003: Remove Legacy Code from Repository

**Status:** Accepted
**Date:** 2025-10-15
**Decision Makers:** Development Team, Security Team
**Related:** ATO Remediation Work Program

## Context

The `old/` directory contained a previous iteration of Elspeth using the 'dmp'
module namespace. This code is no longer used by the current system and has been
superseded by the refactored architecture.

During the ATO (Authority to Operate) architectural assessment, this legacy code
was identified as a medium-risk item:

- **Risk:** Potential confusion for maintainers
- **Risk:** Accidental execution if not clearly segregated
- **Risk:** Increases audit surface unnecessarily
- **Risk:** Violates "least functionality" principle (ISM requirement)

## Decision

We will **remove the `old/` directory** from the active repository and archive it
externally for historical reference.

## Rationale

1. **Security:** Reduces attack surface and eliminates accidental execution risk
2. **Compliance:** Aligns with ISM "least functionality" control
3. **Maintainability:** Reduces confusion for new developers
4. **Audit:** Simplifies code audits by removing unused code
5. **History Preserved:** Git history maintains complete record

## Alternatives Considered

### 1. Keep old/ with Clear Documentation
- **Rejected:** Still increases audit burden and confusion risk
- Documentation alone doesn't eliminate accidental use risk

### 2. Move to old.backup/ or archive/ Directory
- **Rejected:** Still present in repository, still part of deployable package
- Would still be flagged in security scans

### 3. Keep in Separate Branch
- **Rejected:** Branches can still be merged accidentally
- Doesn't remove from main deployment

## Implementation

1. ✅ Verify no active code references `old/` (grep searches)
2. ✅ Archive to `../elspeth-archive/legacy-code-2025-10-15/`
3. ✅ Remove via `git rm -r old/`
4. ✅ Update `.gitignore` to prevent recreation
5. ✅ Document in this ADR
6. ⏳ Update ARCHITECTURAL_REVIEW_2025.md to note removal
7. ⏳ Verify all tests still pass

## Consequences

### Positive
- Cleaner codebase
- Faster security audits
- Less confusion for maintainers
- Meets ATO requirements
- Simpler deployment package

### Negative
- Historical reference requires looking at archive (minor)
- Cannot easily diff old vs new in same repo (can use git history)

### Mitigation
- Archive preserved with clear documentation
- Git history maintains complete record
- ADR documents decision rationale

## Archive Location

**External Archive:** `../elspeth-archive/legacy-code-2025-10-15/`

**Git Commit Before Removal:** `<will be filled in after commit>`

## Verification

After removal, the following must be verified:

```bash
# No old/ directory
[ ! -d "old/" ] && echo "✅ Removed"

# No imports from old code
! grep -r "from old\." src/ tests/ && echo "✅ No imports"

# All tests pass
python -m pytest tests/ && echo "✅ Tests pass"

# Verification script passes
./scripts/verify-no-legacy-code.sh && echo "✅ Verified"
```

## References

- ATO Remediation Work Program: `docs/ATO_REMEDIATION_WORK_PROGRAM.md`
- ATO Assessment: `external/1. ARCHITECTURAL DOCUMENT SET.pdf`
- ISM Controls: <link to ISM documentation>

## Notes

This decision was made as part of the ATO remediation effort. The legacy code
had already been deprecated and was not used by any active system components.

If future development requires reference to old architecture decisions, consult:
1. This ADR and related documentation
2. Git history for the main repository
3. The external archive (read-only)

---

**Approved By:**
- [ ] Development Team Lead
- [ ] Security Team
- [ ] ATO Sponsor

**Date Implemented:** 2025-10-15
**Verification Date:** <to be filled>
EOF

echo "✅ ADR created"
```

#### 2.5: Commit the Changes (15 minutes)

```bash
# Stage all changes
git add -A

# Review what will be committed
git status
git diff --staged --summary

# Create the commit
git commit -m "fix: remove legacy code from repository (ATO remediation MF-1)

Removes the old/ directory containing legacy 'dmp' namespace code that is
no longer used by the active system.

Changes:
- Remove old/ directory (archived externally)
- Update .gitignore to prevent recreation
- Add ADR 003 documenting removal decision
- Add verification scripts for legacy code checks

Rationale:
- Reduces attack surface and audit burden
- Eliminates confusion for maintainers
- Meets ISM 'least functionality' requirement
- Required for ATO approval

Archive Location: ../elspeth-archive/legacy-code-2025-10-15/

Related: ATO Remediation Work Program (MF-1)
Refs: docs/ATO_REMEDIATION_WORK_PROGRAM.md
"

# Note the commit hash
git log -1 --oneline
COMMIT_HASH=$(git rev-parse HEAD)

# Update the ADR with the commit hash
sed -i "s/<will be filled in after commit>/$COMMIT_HASH/" \
    docs/architecture/decisions/003-remove-legacy-code.md

# Amend the commit to include the updated ADR
git add docs/architecture/decisions/003-remove-legacy-code.md
git commit --amend --no-edit
```

#### 2.6: Verify Everything Works (30 minutes)

```bash
# Run the verification script
./scripts/verify-no-legacy-code.sh

# Run all tests
python -m pytest tests/ -v

# Run linting
make lint

# Run daily verification
./scripts/daily-verification.sh

# If all pass:
echo "🎉 MF-1 Complete!"
```

### Step 3: Update the Work Program (10 minutes)

```bash
# Open the work program
# Mark MF-1 tasks as complete

# Update your progress tracking
cat >> docs/ATO_PROGRESS.md << 'EOF'
# ATO Remediation Progress

## 2025-10-15

### Completed
- ✅ MF-1: Remove Legacy Code
  - Verified no active references
  - Archived to external location
  - Removed from repository
  - Created ADR 003
  - All tests passing
  - Verification scripts passing

### In Progress
- ⏳ MF-2: Plugin Registry Migration (Starting tomorrow)

### Blockers
- None

### Next Steps
1. Start MF-2: Audit current registry usage
2. Create REGISTRY_MIGRATION_STATUS.md
3. Begin datasource registry migration
EOF

cat docs/ATO_PROGRESS.md
```

## 📅 Daily Routine

Run this every morning before starting work:

```bash
# 1. Daily verification
./scripts/daily-verification.sh

# 2. Review work program
cat docs/ATO_REMEDIATION_WORK_PROGRAM.md | grep "^###" | head -20

# 3. Check progress
cat docs/ATO_PROGRESS.md

# 4. Plan today's work (write down 3 specific tasks)
echo "Today I will:"
echo "1. _______________"
echo "2. _______________"
echo "3. _______________"
```

## 🆘 Getting Help

### If Tests Fail
1. Check the error message carefully
2. Run individual failing test: `python -m pytest tests/path/to/test.py::test_name -v`
3. Check if related to your recent changes
4. Rollback if needed: `git reset --hard HEAD~1`

### If Verification Script Fails
1. Read the error output
2. Search for the specific issue: `grep -r "problem pattern" src/`
3. Fix the issue
4. Re-run verification

### If Blocked
1. Document the blocker in `docs/ATO_PROGRESS.md`
2. Move to next task if possible
3. Escalate to team lead if blocker persists >1 day

## 📊 Tracking Progress

Update `docs/ATO_PROGRESS.md` daily with:
- ✅ Completed tasks
- ⏳ In-progress tasks
- 🚧 Blockers
- 📝 Notes and decisions

## 🎯 Success Metrics

Daily:
- [ ] All tests passing
- [ ] No linting errors
- [ ] Daily verification passing
- [ ] Progress documented

Weekly:
- [ ] At least 2 Must-Fix items completed
- [ ] No new blockers introduced
- [ ] Documentation updated

## 🚦 Red Flags

Stop and escalate if you encounter:
- 🚨 Security vulnerability discovered
- 🚨 Tests failing that can't be fixed in <2 hours
- 🚨 Architecture change needed (not in work program)
- 🚨 External dependency blocker
- 🚨 Multiple days with no progress

## 📚 Key Documents

- **Work Program:** `docs/ATO_REMEDIATION_WORK_PROGRAM.md` (main reference)
- **ATO Assessment:** `external/1. ARCHITECTURAL DOCUMENT SET.pdf` (background)
- **Architecture Docs:** `docs/architecture/` (reference)
- **CLAUDE.md:** Current patterns and conventions

## 🎓 Tips for Success

1. **One task at a time** - Don't start MF-2 until MF-1 is 100% complete
2. **Test frequently** - Run tests after every significant change
3. **Document as you go** - Update progress daily, not at the end
4. **Ask questions** - Better to ask than make wrong assumption
5. **Take breaks** - Better quality with fresh mind
6. **Commit often** - Small commits are easier to review and rollback

---

## Quick Reference Commands

```bash
# Daily verification
./scripts/daily-verification.sh

# Check for legacy code
./scripts/verify-no-legacy-code.sh

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_specific.py -v

# Run linting
make lint

# Check git status
git status

# View work program
cat docs/ATO_REMEDIATION_WORK_PROGRAM.md | less

# Update progress
nano docs/ATO_PROGRESS.md
```

---

**Ready to start? Run these commands:**

```bash
# Verify environment
./scripts/daily-verification.sh

# Start with MF-1
./scripts/verify-no-legacy-code.sh

# Good luck! 🚀
```
