# MkDocs Configuration Templates

This directory contains configuration templates for the formal documentation site.

## Files

### mkdocs.yml.template

**Purpose**: Complete MkDocs configuration with all features enabled

**Usage**:
```bash
# Copy to site-docs/ during Phase 0
cp docs/migration/formal-documentation-site/mkdocs-configs/mkdocs.yml.template site-docs/mkdocs.yml

# Customize:
# 1. Replace "yourusername" with actual GitHub username/org
# 2. Update site_url with deployment URL
# 3. Choose color palette (currently indigo)
# 4. Add logo/favicon paths (if applicable)
```

**Features Included**:
- Material theme with light/dark mode
- Search with suggestions
- mkdocstrings for API docs
- Extensive Markdown extensions (code blocks, admonitions, tabs, mermaid diagrams)
- Navigation structure (all sections)
- Versioning support (mike)
- Social links
- Copyright

**Customization Points**:
- Site metadata (name, description, URL)
- Color palette (`theme.palette`)
- Logo/favicon (`theme.logo`, `theme.favicon`)
- Social links (`extra.social`)
- Navigation structure (`nav`)

## Navigation Structure Philosophy

**Progressive Disclosure**:
1. **Getting Started** (Level 1): Quick wins, immediate value
2. **User Guide** (Level 2): Conceptual understanding
3. **Plugins** (Level 2): Practical how-to
4. **Architecture** (Level 3): Deep understanding
5. **API Reference** (Level 3): Implementation details

**Ordering Rationale**:
- Most common tasks first (Getting Started)
- Conceptual before procedural (User Guide → Plugins)
- Reference material last (API Reference)

## Theme Customization

### Color Palettes

**Current** (Indigo - Security/Trust):
```yaml
primary: indigo
accent: indigo
```

**Alternatives**:
- Blue (Classic, professional)
- Teal (Modern, technical)
- Green (Growth, success)
- Deep Purple (Creative, sophisticated)

### Adding Logo/Favicon

1. Create `site-docs/overrides/assets/` directory
2. Add image files (e.g., `logo.png`, `favicon.png`)
3. Uncomment in `mkdocs.yml`:
   ```yaml
   theme:
     logo: assets/logo.png
     favicon: assets/favicon.png
   ```

## Markdown Extensions Reference

**Code Blocks**:
```python
def example():
    """Syntax highlighted with copy button"""
    return "Hello, World!"
```

**Admonitions**:
```markdown
!!! note "Title"
    Call-out box content

!!! warning
    Warning message

??? info "Collapsible"
    Click to expand
```

**Tabs**:
```markdown
=== "Python"
    ```python
    print("Hello")
    ```

=== "Bash"
    ```bash
    echo "Hello"
    ```
```

**Task Lists**:
```markdown
- [x] Completed task
- [ ] Pending task
```

**Mermaid Diagrams**:
````markdown
```mermaid
graph LR
    A[Source] --> B[Transform]
    B --> C[Sink]
```
````

## Versioning Setup (Phase 4)

**Install mike**:
```bash
pip install mike
```

**Deploy versions**:
```bash
# Deploy version 1.0
mike deploy 1.0 latest --update-aliases
mike set-default latest

# Deploy version 1.1
mike deploy 1.1 latest --update-aliases
```

**List versions**:
```bash
mike list
```

## CI/CD Integration

See `02-IMPLEMENTATION-PLAN.md` Phase 4 for GitHub Actions workflow.

**Key commands**:
- `mkdocs build --strict`: Fail on warnings (use in CI)
- `mkdocs serve`: Local preview (hot-reload)
- `mkdocs gh-deploy`: Deploy to GitHub Pages

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
