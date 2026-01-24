# Bug Triage Scripts

Scripts to execute the bug reorganization from the 2026-01-24 triage report.

## Execution Order

Run these scripts in order:

1. **01-promote-pending-bugs.sh**
   - Promotes 18 pending bugs to open/
   - Safe to run (just moves files)

2. **02-close-obe-bugs.sh**
   - Closes 8 OBE (Overtaken By Events) bugs
   - Adds resolution markers
   - Moves to closed/

3. **03-close-lost-bugs.sh**
   - Closes 8 LOST bugs (experimental features, unclear impact)
   - Adds resolution markers
   - Moves to closed/

4. **04-create-subsystem-dirs.sh**
   - Creates by-subsystem/ and by-priority/ directory structures
   - Prepares for symlink organization

5. **(Manual) Create symlinks**
   - Symlink bugs from open/ to by-subsystem/ and by-priority/
   - Allows dual organization without duplication

## Usage

```bash
cd /home/john/elspeth-rapid

# Make scripts executable
chmod +x docs/bugs/scripts/*.sh

# Run in order
./docs/bugs/scripts/01-promote-pending-bugs.sh
./docs/bugs/scripts/02-close-obe-bugs.sh
./docs/bugs/scripts/03-close-lost-bugs.sh
./docs/bugs/scripts/04-create-subsystem-dirs.sh

# Then manually create symlinks or use a script generator
```

## What Changes

**Before:**
- 73 open bugs in flat open/ directory
- 34 pending bugs in pending/
- 74 closed bugs in closed/

**After:**
- 91 open bugs in open/ (73 + 18 promoted)
- 16 pending bugs (34 - 18 promoted - 16 closed)
- 90 closed bugs (74 + 16 closed)
- Organized by subsystem and priority via symlinks

## Safety

All scripts:
- Use `set -e` to fail fast on errors
- Check file existence before moving
- Add resolution markers to closed bugs
- Print progress and warnings
- Are idempotent (safe to re-run)

## Validation

After running, verify:

```bash
# Count bugs in each status
ls -1 docs/bugs/open/*.md | wc -l      # Should be ~91
ls -1 docs/bugs/pending/*.md | wc -l   # Should be ~16
ls -1 docs/bugs/closed/*.md | wc -l    # Should be ~90

# Check no bugs were lost
find docs/bugs -name "*.md" -type f | grep -E "(P[0-3]|2026-)" | wc -l
```

## Next Steps

After running scripts:
1. Review the triage report (BUG-TRIAGE-REPORT-2026-01-24.md)
2. Create symlinks for dual organization
3. Update BUGS.md with new structure
4. Begin P0 bug fixes (7 critical bugs identified)
