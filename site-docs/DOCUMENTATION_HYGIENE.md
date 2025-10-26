# Documentation Hygiene Policy

**Last Updated**: 2025-10-26
**Status**: Active (Phase 2 - Generate-on-Demand)
**Migration Date**: 2025-10-26

---

## Problem Statement

Auto-generated documentation files can become **stale** if plugin source code changes but documentation isn't regenerated. This creates:

1. **Security Risk**: Users configure plugins incorrectly based on outdated security metadata
2. **Maintenance Burden**: Merge conflicts on generated files
3. **Trust Erosion**: Documentation doesn't match implementation

---

## Phased Implementation

### Phase 1: CI Staleness Detection (COMPLETED)

**Status**: ✅ Completed (2025-10-26)
**Duration**: Workflow stabilized after mkdocstrings fix

**Approach**:
- Generated files (`generated-*.md`) **ARE committed** to git
- CI checks generated files are up-to-date on every PR
- Build fails if generated docs are stale

**Files Tracked**:
```
site-docs/docs/api-reference/plugins/generated-datasources.md
site-docs/docs/api-reference/plugins/generated-transforms.md
site-docs/docs/api-reference/plugins/generated-middlewares.md
site-docs/docs/api-reference/plugins/generated-sinks.md
site-docs/docs/api-reference/plugins/generated-aggregators.md
site-docs/docs/api-reference/plugins/generated-baselines.md
site-docs/docs/plugins/generated-catalogue.md
```

**CI Enforcement**: `.github/workflows/docs.yml`

```yaml
- name: Check generated docs are up-to-date
  run: |
    python scripts/generate_plugin_docs.py
    if git diff --quiet site-docs/docs/plugins/generated-catalogue.md \
                      site-docs/docs/api-reference/plugins/generated-*.md; then
      echo "✅ Generated documentation is up-to-date"
    else
      echo "❌ ERROR: Generated documentation is stale!"
      exit 1
    fi
```

**Pros**:
- ✅ Docs visible in PR reviews (GitHub UI)
- ✅ Works offline without regeneration
- ✅ Gradual migration path

**Cons**:
- ❌ Merge conflicts on generated files
- ❌ Git history pollution
- ❌ Can commit stale docs (caught in CI, not locally)

---

### Phase 2: Generate-on-Demand (ACTIVE)

**Status**: ✅ Active (2025-10-26)
**Trigger**: mkdocstrings fully functional, workflow stabilized

**Approach**:
- Generated files **IGNORED** by git (`.gitignore`)
- Generated locally via `make docs-generate` before `make docs-build`
- Generated automatically in CI/CD

**Migration Steps** (COMPLETED 2025-10-26):

1. ✅ **Updated `.gitignore`**:
   ```gitignore
   site-docs/docs/api-reference/plugins/generated-*.md
   site-docs/docs/plugins/generated-catalogue.md
   ```

2. ✅ **Removed from git**:
   ```bash
   git rm --cached site-docs/docs/api-reference/plugins/generated-*.md
   git rm --cached site-docs/docs/plugins/generated-catalogue.md
   git commit -m "Docs: Migrate to Phase 2 (generate-on-demand)"
   ```

3. ✅ **Updated CI check** (reverse logic):
   ```yaml
   - name: Ensure generated docs are not committed (Phase 2)
     run: |
       if git ls-files 'site-docs/docs/**/generated-*.md' | grep -q .; then
         echo "❌ ERROR: Generated files should not be committed!"
         exit 1
       fi
   ```

4. ⏸️ **Document in CONTRIBUTING.md** (TODO):
   > Run `make docs-generate` before building documentation locally.

**Pros**:
- ✅ Always fresh (regenerated every build)
- ✅ No merge conflicts on generated files
- ✅ Smaller git repo
- ✅ Aligns with "code is source of truth" philosophy

**Cons**:
- ❌ Can't preview generated docs in GitHub PR UI
- ❌ Contributors need extra setup step
- ❌ Offline builds require generator run

---

## Rationale: Why Phase 2 is Better Long-Term

### Alignment with Elspeth Philosophy

**Lockfile Analogy**:
- `requirements-dev.lock` is **generated** from `pyproject.toml` (not hand-edited)
- `generated-*.md` should be **generated** from plugin source code (not hand-edited)
- Both are **derived artifacts** that should be reproducible

**Security Alignment**:
- Elspeth enforces hash-pinned dependencies for supply chain integrity
- Elspeth should enforce fresh documentation for "documentation supply chain integrity"
- Stale docs = silent security bypass vector

**Fail-Fast Philosophy** (ADR-001):
- Phase 1: Fails in CI (late detection)
- Phase 2: Fails at build time (early detection)
- Phase 2 better aligns with "fail before data retrieval" principle

---

## Developer Workflow

### Phase 1 (Legacy - No Longer Used)

```bash
# Make changes to plugin source code
vim src/elspeth/plugins/nodes/sinks/my_sink.py

# Regenerate docs
make docs-generate

# Review changes
git diff site-docs/docs/api-reference/plugins/generated-sinks.md

# Commit both source and generated files
git add src/elspeth/plugins/nodes/sinks/my_sink.py
git add site-docs/docs/api-reference/plugins/generated-sinks.md
git commit -m "Feat: Add MySink plugin"

# CI checks generated files are up-to-date ✅
```

### Phase 2 (Current Workflow)

```bash
# Make changes to plugin source code
vim src/elspeth/plugins/nodes/sinks/my_sink.py

# Commit ONLY source code (generated files ignored)
git add src/elspeth/plugins/nodes/sinks/my_sink.py
git commit -m "Feat: Add MySink plugin"

# CI regenerates docs and builds ✅
# Local preview: make docs-generate && make docs-serve
```

---

## Additional Hygiene Checks (Optional Enhancements)

### Markdown Linting

```yaml
- name: Lint markdown (exclude generated)
  run: |
    markdownlint-cli2 "site-docs/docs/**/*.md" \
      --ignore "**/generated-*.md"
```

### Broken Link Detection

```yaml
- name: Check for broken links
  run: |
    linkchecker site-docs/site/ \
      --check-extern \
      --ignore-url="^https://github.com/johnm-dta/elspeth"
```

### Spell Checking

```yaml
- name: Spell check (exclude generated)
  run: |
    cspell "site-docs/docs/**/*.md" \
      --exclude "**/generated-*.md"
```

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-10-26 | Adopt Phase 1 (CI staleness checks) | Gradual migration, workflow stabilization |
| 2025-10-26 | **Migrate to Phase 2 (gitignore)** | mkdocstrings fixed, workflow stable, alignment with code-as-source-of-truth philosophy |

---

## See Also

- `.github/workflows/docs.yml` - CI enforcement
- `scripts/generate_plugin_docs.py` - Generator implementation
- `Makefile` - `docs-generate` target
- `.gitignore` - Phase 2 active (generated files ignored)
