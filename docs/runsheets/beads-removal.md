# Runsheet: Remove Beads (bd) from a Project

Complete removal of the `bd` (beads) issue tracker from a git repository.
Tested on bd v0.49.6. Adjust paths if your project differs.

## Prerequisites

- `bd` CLI available on PATH
- Working directory is the project root
- No uncommitted work you care about in the beads-sync branch

## Phase 1: Stop the daemon

```bash
bd daemon status                      # Check if running
bd daemon stop ~/your-project         # Stop it (use absolute path)
```

## Phase 2: Triage open beads (optional)

If you want to preserve open bead content before deletion:

```bash
# List all open beads
bd list

# Show full details for each
bd show <bead-id>

# Export to markdown files, or your new system, then:
bd delete <id1> <id2> ... --force
```

Skip this if you've already migrated or don't care about the data.

## Phase 3: Delete the .beads directory

```bash
rm -rf .beads/
```

This removes:
- `beads.db` (SQLite database)
- `beads.db-shm`, `beads.db-wal` (SQLite WAL files)
- `daemon.log`
- Any JSONL export files

## Phase 4: Remove git hooks

bd installs 4 hooks as thin shims. The `pre-commit` hook is typically from
the pre-commit framework, NOT beads — check before deleting.

```bash
# Inspect each hook first — look for "bd-shim" or "bd hook" in the content
head -5 .git/hooks/post-checkout .git/hooks/post-merge \
       .git/hooks/prepare-commit-msg .git/hooks/pre-push

# Delete the bd hooks (all have "bd-shim v1" header)
rm .git/hooks/post-checkout
rm .git/hooks/post-merge
rm .git/hooks/prepare-commit-msg
rm .git/hooks/pre-push
```

**Do NOT delete `.git/hooks/pre-commit`** unless it's also a bd hook.
It's usually the pre-commit framework hook.

## Phase 5: Remove git config entries

```bash
# List what's there
git config --local --list | grep -iE 'bead|bd'

# Remove merge driver
git config --local --unset merge.beads.driver
git config --local --unset merge.beads.name

# Remove beads-sync branch tracking
git config --local --remove-section branch.beads-sync 2>/dev/null

# Remove beads role
git config --local --unset beads.role
```

## Phase 6: Clean .gitattributes

Remove the beads merge driver lines from `.gitattributes`:

```
# Use bd merge for beads JSONL files          ← delete this
.beads/issues.jsonl merge=beads               ← delete this
```

If .gitattributes is now empty, you can delete it entirely.

## Phase 7: Remove beads-sync worktree, branch, and refs

**IMPORTANT:** The worktree must be removed BEFORE the branch can be deleted.
`git branch -D` refuses to delete a branch checked out in a worktree.

bd stores the worktree in two places:
- `.git/beads-worktrees/` — the checkout directory
- `.git/worktrees/beads-sync/` — git's internal worktree metadata

Both must be removed, then pruned.

```bash
# Step 1: Remove the worktree checkout directory
rm -rf .git/beads-worktrees/

# Step 2: Remove git's worktree metadata (this is the one that blocks branch deletion)
rm -rf .git/worktrees/beads-sync/

# Step 3: Prune stale worktree references
git worktree prune

# Step 4: Verify worktree is gone (should show only main worktree)
git worktree list

# Step 5: NOW the branch can be deleted
git branch -D beads-sync 2>/dev/null

# Step 6: Delete remote tracking ref
git update-ref -d refs/remotes/origin/beads-sync 2>/dev/null

# Step 7: Delete reflogs
rm -f .git/logs/refs/heads/beads-sync
rm -f .git/logs/refs/remotes/origin/beads-sync
```

Optionally delete the remote branch too:
```bash
git push origin --delete beads-sync   # Only if you own the remote
```

## Phase 8: Untrack .beads/ files from git

bd tracks JSONL files in git (for sync). Some may be under sparse-checkout,
which requires `--sparse` flag.

```bash
# Check what's tracked
git ls-files .beads/

# Remove from index (use --sparse if you get sparse-checkout errors)
git rm -r --cached .beads/ 2>/dev/null
git rm -r --cached --sparse .beads/ 2>/dev/null

# Delete the physical directory (if Phase 3 left anything behind)
rm -rf .beads/
```

## Phase 9: Verify

```bash
# No beads references in git config
git config --local --list | grep -iE 'bead|bd'    # Should be empty

# No bd hooks
ls .git/hooks/ | grep -v sample                     # Only pre-commit (if using pre-commit framework)

# No .beads directory
ls -la .beads/ 2>&1                                 # Should say "No such file"

# No tracked .beads files
git ls-files .beads/                                # Should be empty

# No beads worktrees
git worktree list                                   # Should show only main worktree
ls .git/worktrees/ 2>&1                             # Should say "No such file" or be empty

# No beads branches
git branch -a | grep bead                           # Should be empty

# .gitattributes clean
cat .gitattributes                                  # No beads lines
```

## Phase 10: Commit the cleanup

```bash
git add .gitattributes
git commit -m "chore: remove beads issue tracker

Migrated open beads to [your new system]. Removed:
- .beads/ database and daemon
- bd git hooks (post-checkout, post-merge, prepare-commit-msg, pre-push)
- beads merge driver from .gitattributes and git config
- beads-sync branch and worktree data"
```

## Notes

- The `beads-sync` branch on the remote can be deleted if no other clones use it.
- If other developers have beads installed, they'll see harmless "bd command not
  found" warnings until they pull this cleanup and the hooks are gone from their
  `.git/hooks/`. The shims exit 0 gracefully when bd is missing.
- bd does NOT modify `.gitignore` — no cleanup needed there.

## Gotchas Encountered During Testing

1. **Worktree double-storage.** bd creates a checkout at `.git/beads-worktrees/`
   but git's actual worktree metadata lives at `.git/worktrees/beads-sync/`.
   Deleting only the former leaves the branch locked. You must delete both and
   run `git worktree prune`.

2. **Sparse-checkout JSONL files.** bd puts `issues.jsonl` and
   `interactions.jsonl` under sparse-checkout. `git rm --cached` fails on these
   unless you pass `--sparse`. Check with `git ls-files .beads/` after the first
   `git rm` pass.

3. **No uninstall command.** bd v0.49.6 has no `bd uninstall` or `bd teardown`.
   All cleanup is manual.
