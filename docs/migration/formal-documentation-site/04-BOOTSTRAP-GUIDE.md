# Bootstrap Guide - Phase 0 Execution

**Document Purpose**: Step-by-step instructions to execute Phase 0 (bootstrap) and get a working local documentation site.

**Estimated Time**: 1-2 hours
**Prerequisites**: None (ready to start immediately)
**Outcome**: Local MkDocs site running at `http://127.0.0.1:8000` with Material theme

---

## Step 1: Create Feature Branch (5 minutes)

```bash
cd /home/john/elspeth

# Create feature branch from current branch
git checkout -b feature/formal-docs-site

# Verify branch
git branch
```

**Checkpoint**: You're on `feature/formal-docs-site` branch

---

## Step 2: Create Directory Structure (10 minutes)

```bash
# Create main site-docs structure
mkdir -p site-docs/docs/{getting-started,user-guide,plugins,architecture,compliance,operations,api-reference}
mkdir -p site-docs/overrides

# Create placeholder files
touch site-docs/docs/index.md
touch site-docs/docs/getting-started/.gitkeep
touch site-docs/docs/user-guide/.gitkeep
touch site-docs/docs/plugins/.gitkeep
touch site-docs/docs/architecture/.gitkeep
touch site-docs/docs/compliance/.gitkeep
touch site-docs/docs/operations/.gitkeep
touch site-docs/docs/api-reference/.gitkeep

# Verify structure
tree site-docs -L 3
```

**Expected Output**:
```
site-docs
├── docs
│   ├── api-reference
│   ├── architecture
│   ├── compliance
│   ├── getting-started
│   ├── index.md
│   ├── operations
│   ├── plugins
│   └── user-guide
└── overrides
```

**Checkpoint**: Directory structure matches expected output

---

## Step 3: Create Requirements File (10 minutes)

**Create `site-docs/requirements.txt`**:

```bash
cat > site-docs/requirements.txt <<'EOF'
mkdocs>=1.5.0
mkdocs-material>=9.5.0
mkdocstrings[python]>=0.24.0
pymdown-extensions>=10.7
EOF
```

**Verify**:
```bash
cat site-docs/requirements.txt
```

**Add to Development Lockfile**:

```bash
# Option A: Recompile entire dev lockfile (recommended)
# (Follow project's standard lockfile procedure)

# Option B: Install temporarily for testing (Phase 0 only)
source .venv/bin/activate
pip install -r site-docs/requirements.txt
```

**Checkpoint**: MkDocs packages installed in virtual environment

---

## Step 4: Create mkdocs.yml Configuration (20 minutes)

**Copy template**:

```bash
cp docs/migration/formal-documentation-site/mkdocs-configs/mkdocs.yml.template site-docs/mkdocs.yml
```

**If template doesn't exist yet, create manually**:

```bash
cat > site-docs/mkdocs.yml <<'EOF'
site_name: Elspeth Documentation
site_description: Extensible Layered Secure Pipeline Engine for Transformation and Handling
site_url: https://yourusername.github.io/elspeth  # Update with your actual URL

repo_url: https://github.com/yourusername/elspeth  # Update with your repo
repo_name: yourusername/elspeth
edit_uri: edit/main/site-docs/docs/

theme:
  name: material
  palette:
    # Light mode
    - scheme: default
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    # Dark mode
    - scheme: slate
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

  features:
    - navigation.tabs           # Top-level tabs
    - navigation.sections       # Expandable sections
    - navigation.expand         # Auto-expand subsections
    - navigation.top            # "Back to top" button
    - search.suggest            # Search suggestions
    - search.highlight          # Highlight search terms
    - content.code.copy         # Copy button on code blocks
    - content.code.annotate     # Code annotations

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [../src]  # Point to source code
          options:
            docstring_style: google
            show_source: true
            show_root_heading: true

markdown_extensions:
  - admonition              # Call-out blocks
  - pymdownx.details        # Collapsible admonitions
  - pymdownx.superfences    # Code blocks with syntax highlighting
  - pymdownx.tabbed:        # Tabbed content
      alternate_style: true
  - pymdownx.highlight:     # Syntax highlighting
      anchor_linenums: true
  - pymdownx.inlinehilite   # Inline code highlighting
  - pymdownx.snippets       # Include file snippets
  - tables                  # Table support
  - attr_list               # Add CSS classes to elements
  - md_in_html              # Markdown inside HTML

nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/installation.md
    - Quickstart: getting-started/quickstart.md
    - First Experiment: getting-started/first-experiment.md
  - User Guide:
    - Security Model: user-guide/security-model.md
    - Configuration: user-guide/configuration.md
  - Plugins:
    - Overview: plugins/overview.md
    - Datasources: plugins/datasources.md
    - Transforms: plugins/transforms.md
    - Sinks: plugins/sinks.md
  - Architecture:
    - Overview: architecture/overview.md
  - Compliance:
    - Security Controls: compliance/security-controls.md
  - Operations:
    - Deployment: operations/deployment.md
  - API Reference:
    - Core: api-reference/core.md
    - Security: api-reference/security.md

extra:
  version:
    provider: mike  # For versioning support (Phase 4)

EOF
```

**Customize**:
1. Replace `yourusername` with actual GitHub username/org
2. Update `site_url` if you know the final deployment URL

**Checkpoint**: `site-docs/mkdocs.yml` exists and has correct repo details

---

## Step 5: Write Skeleton index.md (15 minutes)

```bash
cat > site-docs/docs/index.md <<'EOF'
# Elspeth Documentation

**Extensible Layered Secure Pipeline Engine for Transformation and Handling**

Elspeth is a security-first orchestration platform for LLM experimentation and general-purpose sense-decide-act workflows.

## Core Features

- **Bell-LaPadula Multi-Level Security (MLS)** enforcement
- **Plugin-based architecture** (sources → transforms → sinks)
- **Artifact signing** (HMAC-SHA256, RSA-PSS, ECDSA)
- **Comprehensive audit logging**
- **Fail-fast security validation**

## Architecture

```
┌──────────────┐      ┌───────────────┐      ┌──────────┐
│  Datasources │  →   │  Transforms   │  →   │  Sinks   │
│  (CSV, DB)   │      │  (LLM, etc)   │      │  (Excel) │
└──────────────┘      └───────────────┘      └──────────┘
        ↓                     ↓                    ↓
    ┌────────────────────────────────────────────────┐
    │       Security Level Enforcement (MLS)          │
    └────────────────────────────────────────────────┘
```

## Quick Links

- [Installation](getting-started/installation.md) - Get Elspeth running
- [Quickstart](getting-started/quickstart.md) - 5-minute hello world
- [Security Model](user-guide/security-model.md) - Understand Bell-LaPadula MLS
- [Plugin Catalogue](plugins/overview.md) - Available plugins
- [API Reference](api-reference/core.md) - Detailed API docs

## Project Status

- **Version**: 0.1.0-dev (pre-release)
- **Documentation**: Work in progress
- **License**: [Check repository for details]

---

*This documentation is versioned alongside the codebase. For developer documentation (ADRs, refactoring methodology, migration plans), see the `docs/` directory in the repository.*

EOF
```

**Checkpoint**: `site-docs/docs/index.md` exists and has project overview

---

## Step 6: Test Local Preview (10 minutes)

```bash
cd site-docs
mkdocs serve
```

**Expected Output**:
```
INFO    -  Building documentation...
INFO    -  Cleaning site directory
INFO    -  Documentation built in 0.42 seconds
INFO    -  [12:34:56] Watching paths for changes: 'docs', 'mkdocs.yml'
INFO    -  [12:34:56] Serving on http://127.0.0.1:8000/
```

**Open in Browser**: http://127.0.0.1:8000

**Validate** :
- ✅ Site loads without errors
- ✅ Material theme applied (indigo colors)
- ✅ Landing page displays correctly
- ✅ Navigation structure shows all sections
- ✅ Search box visible (top right)
- ✅ Dark mode toggle works (click moon/sun icon)
- ✅ Mobile preview responsive (resize browser window)

**Troubleshooting**:

**Error: "Config file 'mkdocs.yml' does not exist"**
- Solution: Ensure you're in `site-docs/` directory

**Error: "No module named 'mkdocs'"**
- Solution: Activate virtual environment, reinstall requirements

**Warning: "Navigation contains items without page"**
- Solution: Expected (placeholder pages don't exist yet), ignore for now

**Checkpoint**: Local preview works, no errors in console

---

## Step 7: Update .gitignore (5 minutes)

```bash
cd /home/john/elspeth

# Append to .gitignore
cat >> .gitignore <<'EOF'

# MkDocs build output
/site/
/site-docs/site/
EOF
```

**Verify**:
```bash
tail -5 .gitignore
```

**Checkpoint**: `.gitignore` includes `site/` and `site-docs/site/`

---

## Step 8: Update Makefile (10 minutes)

```bash
cd /home/john/elspeth

# Add to Makefile (append at end)
cat >> Makefile <<'EOF'

# ============================================================================
# Documentation Targets
# ============================================================================

.PHONY: docs-serve
docs-serve:  ## Serve formal documentation locally
	cd site-docs && mkdocs serve

.PHONY: docs-build
docs-build:  ## Build formal documentation
	cd site-docs && mkdocs build --strict

.PHONY: docs-deploy
docs-deploy:  ## Deploy documentation to GitHub Pages
	cd site-docs && mkdocs gh-deploy --force

EOF
```

**Test**:
```bash
make docs-serve
```

**Should start local preview from project root**

**Checkpoint**: `make docs-serve` works from project root

---

## Step 9: Commit Phase 0 (10 minutes)

```bash
cd /home/john/elspeth

# Stage changes
git add site-docs/
git add .gitignore
git add Makefile

# Check status
git status

# Commit
git commit -m "$(cat <<'EOF'
Docs: Bootstrap formal documentation site (Phase 0)

Create MkDocs + Material site structure:
- site-docs/ folder with sections (getting-started, user-guide, plugins, architecture, compliance, operations, api-reference)
- mkdocs.yml configuration (Material theme, search, mkdocstrings, markdown extensions)
- Skeleton index.md (project overview)
- .gitignore updates (ignore site/ build output)
- Makefile targets (docs-serve, docs-build, docs-deploy)

Local preview working at http://127.0.0.1:8000

Next: Phase 1 content migration (Getting Started, Security Model, Plugin Catalogue, Configuration, Architecture)

Tracked in: docs/migration/formal-documentation-site/

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

**Checkpoint**: Phase 0 changes committed to feature branch

---

## Phase 0 Complete! ✅

### What You Have Now

- ✅ Working local documentation site at `http://127.0.0.1:8000`
- ✅ Material theme with custom colors (indigo)
- ✅ Navigation structure defined (all sections)
- ✅ Search enabled
- ✅ Dark mode toggle
- ✅ Mobile-responsive
- ✅ Makefile shortcuts (`make docs-serve`)
- ✅ Git tracking (feature branch)

### Exit Criteria Met

- ✅ `mkdocs serve` runs without errors or warnings
- ✅ Landing page displays with Material theme
- ✅ Search works
- ✅ Navigation structure defined
- ✅ Theme customized (indigo, not default blue)
- ✅ Dark mode toggle functions
- ✅ Mobile preview responsive

### Next Steps

**Immediate**:
1. Keep local preview running (`make docs-serve`)
2. Start Phase 1 content migration

**Phase 1 (Next Session)**:
1. Write Getting Started guide (installation, quickstart, first experiment)
2. Distill Security Model from ADRs
3. Refine Plugin Catalogue
4. Distill Configuration Guide
5. Distill Architecture Overview

**Use**: `docs/migration/formal-documentation-site/03-CONTENT-MIGRATION-MATRIX.md` for tracking

---

## Quick Reference Commands

```bash
# Start local preview
make docs-serve
# OR
cd site-docs && mkdocs serve

# Build static site
make docs-build
# OR
cd site-docs && mkdocs build --strict

# Check for warnings (strict mode)
cd site-docs && mkdocs build --strict

# Stop preview
# Press Ctrl+C in terminal
```

---

## Troubleshooting

### Preview Not Updating

**Problem**: Changes to markdown files don't show in browser

**Solutions**:
1. Hard refresh: Ctrl+Shift+R (Linux/Windows) or Cmd+Shift+R (Mac)
2. Restart `mkdocs serve`
3. Clear browser cache

### Warning: "Navigation contains items without page"

**Problem**: MkDocs warns about placeholder pages in nav

**Solution**: Expected during Phase 0 (pages don't exist yet). Will resolve in Phase 1 when content is written.

### Error: "Page not found"

**Problem**: Clicking navigation link shows 404

**Solution**: Expected (placeholder pages don't exist yet). Will resolve in Phase 1.

### Port Already in Use

**Problem**: `Address already in use` error

**Solutions**:
1. Kill existing MkDocs process: `pkill -f "mkdocs serve"`
2. Use different port: `mkdocs serve --dev-addr 127.0.0.1:8001`

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
