# Beads Replacement — Agent-Native Issue Tracker

**Date:** 2026-02-11
**Status:** Draft
**Purpose:** Replace .beads with an agent-first issue tracker. SQLite + MCP + thin CLI. No daemon, no git sync, no breakage.

## 1. Design Principles

1. **Agent-first, human-friendly** — MCP is the primary interface, thin CLI for humans
2. **Pre-computed context** — agents read a summary file, not raw queries
3. **Plan-as-issues** — implementation plans live as milestone→phase→step hierarchies
4. **Loose fields** — core schema + JSON metadata bag, works for bugs/requirements/milestones/anything
5. **No moving parts** — SQLite file, no daemon, no sync, no socket
6. **Migrate, don't abandon** — carry over 646 existing beads issues

## 2. Data Model

SQLite, single file, WAL mode.

### `issues` table

```sql
CREATE TABLE issues (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    priority    INTEGER NOT NULL DEFAULT 2,
    type        TEXT NOT NULL DEFAULT 'task',
    parent_id   TEXT REFERENCES issues(id),
    assignee    TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    closed_at   TEXT,
    description TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    fields      TEXT DEFAULT '{}',

    CHECK (status IN ('open', 'in_progress', 'closed')),
    CHECK (priority BETWEEN 0 AND 4)
);

CREATE INDEX idx_issues_status ON issues(status);
CREATE INDEX idx_issues_type ON issues(type);
CREATE INDEX idx_issues_parent ON issues(parent_id);
CREATE INDEX idx_issues_priority ON issues(priority);
```

### `dependencies` table

```sql
CREATE TABLE dependencies (
    issue_id       TEXT NOT NULL REFERENCES issues(id),
    depends_on_id  TEXT NOT NULL REFERENCES issues(id),
    type           TEXT NOT NULL DEFAULT 'blocks',
    created_at     TEXT NOT NULL,
    PRIMARY KEY (issue_id, depends_on_id)
);

CREATE INDEX idx_deps_depends_on ON dependencies(depends_on_id);
```

### `events` table

```sql
CREATE TABLE events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id   TEXT NOT NULL REFERENCES issues(id),
    event_type TEXT NOT NULL,
    actor      TEXT DEFAULT '',
    old_value  TEXT,
    new_value  TEXT,
    comment    TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_events_issue ON events(issue_id);
CREATE INDEX idx_events_created ON events(created_at);
```

### `comments` table

```sql
CREATE TABLE comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id   TEXT NOT NULL REFERENCES issues(id),
    author     TEXT DEFAULT '',
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### `labels` table

```sql
CREATE TABLE labels (
    issue_id TEXT NOT NULL REFERENCES issues(id),
    label    TEXT NOT NULL,
    PRIMARY KEY (issue_id, label)
);
```

### `templates` table

```sql
CREATE TABLE templates (
    type         TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description  TEXT DEFAULT '',
    fields_schema TEXT NOT NULL
);
```

## 3. Issue Type Templates

Templates define the advisory field schema for each issue type. Stored in `templates` table, loaded at startup. Fields are **not enforced** — they guide agents and CLI on what to populate.

Field definition format:
```json
{"name": "severity", "type": "enum", "options": ["critical","major","minor","cosmetic"], "default": "major", "description": "Impact severity"}
```

Field types: `text`, `enum`, `number`, `boolean`, `date`, `url`, `list`.

### Bug
```json
{
  "type": "bug",
  "display_name": "Bug Report",
  "description": "Defects, regressions, and unexpected behavior",
  "fields_schema": [
    {"name": "severity", "type": "enum", "options": ["critical","major","minor","cosmetic"], "default": "major", "description": "Impact severity"},
    {"name": "component", "type": "text", "description": "Affected subsystem (e.g. engine/processor, plugins/llm)"},
    {"name": "steps_to_reproduce", "type": "text", "description": "Numbered steps to trigger the bug"},
    {"name": "expected_behavior", "type": "text", "description": "What should happen"},
    {"name": "actual_behavior", "type": "text", "description": "What actually happens"},
    {"name": "environment", "type": "text", "description": "Python version, OS, relevant config"},
    {"name": "error_output", "type": "text", "description": "Stack trace or error message"},
    {"name": "root_cause", "type": "text", "description": "Identified root cause (filled during triage)"},
    {"name": "fix_verification", "type": "text", "description": "How to verify the fix works"}
  ]
}
```

### Requirement
```json
{
  "type": "requirement",
  "display_name": "Requirement",
  "description": "Functional/non-functional requirements, user stories, constraints",
  "fields_schema": [
    {"name": "requirement_type", "type": "enum", "options": ["functional","non_functional","constraint","user_story"], "default": "functional", "description": "Classification"},
    {"name": "stakeholder", "type": "text", "description": "Who needs this"},
    {"name": "rationale", "type": "text", "description": "Why this is needed"},
    {"name": "acceptance_criteria", "type": "text", "description": "Testable conditions for done (Given/When/Then or checklist)"},
    {"name": "source", "type": "text", "description": "Where this requirement came from"},
    {"name": "constraints", "type": "text", "description": "Technical or business constraints"},
    {"name": "out_of_scope", "type": "text", "description": "Explicitly excluded"}
  ]
}
```

### Milestone
```json
{
  "type": "milestone",
  "display_name": "Milestone",
  "description": "Top-level delivery marker. Contains phases.",
  "fields_schema": [
    {"name": "target_date", "type": "date", "description": "Target completion date"},
    {"name": "success_criteria", "type": "text", "description": "How we know this milestone is achieved"},
    {"name": "deliverables", "type": "list", "description": "Concrete outputs"},
    {"name": "risks", "type": "text", "description": "Known risks and mitigations"},
    {"name": "scope_summary", "type": "text", "description": "What's in and out of scope"}
  ]
}
```

### Phase
```json
{
  "type": "phase",
  "display_name": "Phase",
  "description": "Logical grouping of steps within a milestone",
  "fields_schema": [
    {"name": "sequence", "type": "number", "description": "Execution order within milestone (1, 2, 3...)"},
    {"name": "entry_criteria", "type": "text", "description": "What must be true before this phase starts"},
    {"name": "exit_criteria", "type": "text", "description": "What must be true for this phase to be complete"},
    {"name": "estimated_effort", "type": "text", "description": "Rough effort estimate (e.g. '2-3 sessions')"}
  ]
}
```

### Step
```json
{
  "type": "step",
  "display_name": "Implementation Step",
  "description": "Atomic unit of work within a phase. The work item agents pick up.",
  "fields_schema": [
    {"name": "sequence", "type": "number", "description": "Execution order within phase"},
    {"name": "target_files", "type": "list", "description": "Files expected to be created/modified"},
    {"name": "verification", "type": "text", "description": "How to verify this step is done (test command, manual check)"},
    {"name": "implementation_notes", "type": "text", "description": "Technical guidance, patterns to follow, gotchas"},
    {"name": "estimated_minutes", "type": "number", "description": "Rough time estimate"},
    {"name": "done_definition", "type": "text", "description": "Explicit definition of done"}
  ]
}
```

### Task
```json
{
  "type": "task",
  "display_name": "Task",
  "description": "General-purpose work item",
  "fields_schema": [
    {"name": "context", "type": "text", "description": "Background context"},
    {"name": "done_definition", "type": "text", "description": "How to know this is complete"},
    {"name": "estimated_minutes", "type": "number", "description": "Rough time estimate"}
  ]
}
```

### Feature
```json
{
  "type": "feature",
  "display_name": "Feature",
  "description": "User-facing functionality",
  "fields_schema": [
    {"name": "user_story", "type": "text", "description": "As a [who], I want [what], so that [why]"},
    {"name": "acceptance_criteria", "type": "text", "description": "Testable conditions for done"},
    {"name": "design_notes", "type": "text", "description": "Technical design decisions"},
    {"name": "affected_components", "type": "list", "description": "Subsystems this touches"},
    {"name": "rollback_plan", "type": "text", "description": "How to revert if something goes wrong"}
  ]
}
```

### Epic
```json
{
  "type": "epic",
  "display_name": "Epic",
  "description": "Large body of work containing features/tasks. Uses parent_id for grouping.",
  "fields_schema": [
    {"name": "scope_summary", "type": "text", "description": "What's in and out of scope"},
    {"name": "success_metrics", "type": "text", "description": "How we measure success"},
    {"name": "key_decisions", "type": "text", "description": "Architectural decisions made"},
    {"name": "risks", "type": "text", "description": "Known risks and mitigations"}
  ]
}
```

## 4. Planning Workflow: Plan-as-Issues

Instead of writing plans to markdown files and tracking them separately, plans live as issue hierarchies:

```
Milestone: "RC2.5 SQLite Migration"           (type=milestone)
  └─ Phase 1: "Schema Design"                 (type=phase, parent_id=milestone)
       └─ Step 1.1: "Define core tables"      (type=step, parent_id=phase1)  → READY
       └─ Step 1.2: "Write migration script"  (type=step, parent_id=phase1)  → dep: 1.1
  └─ Phase 2: "Implementation"                (type=phase, parent_id=milestone, dep: phase1)
       └─ Step 2.1: "Build MCP server"        (type=step, parent_id=phase2)  → dep: phase2
       └─ Step 2.2: "Build thin CLI"          (type=step, parent_id=phase2)  → dep: 2.1
  └─ Phase 3: "Cutover"                       (type=phase, parent_id=milestone, dep: phase2)
       └─ Step 3.1: "Migrate 646 issues"      (type=step, parent_id=phase3)  → dep: phase3
```

**Agent workflow:**
1. Read pre-computed summary → sees "Step 1.1 is ready"
2. Open Step 1.1 via MCP → reads `target_files`, `implementation_notes`, `verification`
3. Implement, run verification
4. Close Step 1.1 via MCP → summary regenerates → Step 1.2 unblocks
5. Read summary → "Step 1.2 is ready" → continue

**Benefits over plan files:**
- No markdown file to keep in sync with reality
- Dependencies are explicit and machine-readable
- Progress is automatically tracked (closed steps = done)
- Pre-computed summary shows "what's next" without agent having to parse a plan doc

## 5. Pre-computed Summary File

Auto-regenerated after every mutation (via CLI post-command hook or MCP post-write). Stored at `.beads_tree/agent-context.md`. Read by agents at session start instead of `bd prime`.

Target size: **80-120 lines** — enough to orient, not enough to waste context.

```markdown
# Project Pulse (auto-generated 2026-02-11T15:04:00)

## Vitals
Open: 152 | In Progress: 1 | Ready: 12 | Blocked: 38

## Active Plans
### RC2.5 SQLite Migration [████░░░░░░] 3/8 steps
  Phase 1: Schema Design ✓ (2/2 complete)
  Phase 2: Implementation ▶ (1/4 complete, Step 2.2 ready)
  Phase 3: Cutover ○ (blocked by Phase 2)

## Ready to Work (no blockers, by priority)
- P1 elspeth-42 [bug] "Fix SSRF validation in web.py"
- P1 elspeth-57 [step] "Build thin CLI" (RC2.5 > Phase 2 > Step 2.2)
- P2 elspeth-63 [bug] "Add atomic writes to JSON sink"
- P2 elspeth-71 [task] "Content safety fail-closed"
...12 items total

## In Progress
- elspeth-99 [step] "Build MCP server" (since Feb 11, RC2.5 > Phase 2 > Step 2.1)

## Blocked (top 10 by priority)
- P1 elspeth-80 [step] "Migrate 646 issues" ← blocked by: elspeth-99
- P2 elspeth-85 [task] "Integration tests" ← blocked by: elspeth-80, elspeth-88
...

## Epic Progress
- Auth Refactor    [████░░░░] 4/10 (2 blocked)
- Sink Hardening   [██████░░] 6/8  (1 ready)
- LLM Dedup        [░░░░░░░░] 0/6  (all blocked by Auth)

## Recent Activity (last 24h)
- CLOSED elspeth-41 "Fix gate wiring" (2h ago)
- CREATED elspeth-42 "Fix SSRF validation" (5h ago)
- STATUS elspeth-99 open→in_progress (6h ago)

## Stale (in_progress >3 days, no activity)
- (none)
```

### What gets pre-computed

| Calculation | Live cost | Pre-computed |
|-------------|-----------|--------------|
| "Is issue X ready?" | Join issues + deps, filter open blockers | `is_ready` boolean per issue |
| "What blocks X?" | Recursive dep walk | Flattened blocker list |
| "Epic progress" | Group children by status, count | Fraction + blocked count |
| "Plan progress" | Walk milestone→phase→step hierarchy | Step completion counts |
| "Critical path" | Longest unresolved dep chain | Pre-computed path |
| "Stale items" | Compare timestamps to now | Pre-filtered list |

## 6. MCP Server

Primary interface for agents. Direct SQLite access, no daemon.

### Tools

| Tool | Purpose | Replaces |
|------|---------|----------|
| `get_issue(id)` | Full issue with fields, deps, recent events | `bd show` |
| `list_issues(status?, type?, priority?, parent_id?)` | Filtered list | `bd list` |
| `create_issue(title, type, priority, parent_id?, fields?, deps?)` | Create issue from template | `bd create` |
| `update_issue(id, status?, priority?, title?, fields?, assignee?)` | Update any field | `bd update` |
| `close_issue(id, reason?)` | Close + record event | `bd close` |
| `add_dependency(from_id, to_id, type?)` | Add dep edge | `bd dep add` |
| `remove_dependency(from_id, to_id)` | Remove dep edge | `bd dep remove` |
| `get_ready()` | Pre-computed ready list | `bd ready` |
| `get_blocked()` | Blocked issues + what blocks them | `bd blocked` |
| `get_plan(milestone_id)` | Full milestone→phase→step tree with progress | (new) |
| `add_comment(issue_id, text)` | Add comment | `bd comments add` |
| `search(query)` | Full-text search across title + description | `bd search` |
| `get_template(type)` | Get field schema for an issue type | (new) |
| `get_summary()` | Return the pre-computed summary text | (new — for agents that want it via MCP) |

### Post-mutation hook

Every write operation (create, update, close, add_dependency) triggers summary regeneration:

```python
def _regenerate_summary(self):
    """Rebuild agent-context.md from current DB state. ~50ms for 600 issues."""
    summary = self._compute_summary()
    Path(".beads_tree/agent-context.md").write_text(summary)
```

## 7. Thin CLI

Minimal CLI for human use. Same SQLite, no daemon.

```bash
# Issue CRUD
tracker create "Fix the SSRF bug" --type=bug --priority=1
tracker create "Schema Design" --type=phase --parent=elspeth-100
tracker show elspeth-42
tracker list --status=open --type=bug
tracker update elspeth-42 --status=in_progress
tracker close elspeth-42 --reason="Fixed in commit abc123"

# Dependencies
tracker dep add elspeth-43 elspeth-42     # 43 depends on 42
tracker dep remove elspeth-43 elspeth-42

# Planning
tracker plan elspeth-100                   # Show milestone tree with progress
tracker ready                              # What's unblocked

# Utility
tracker search "SSRF"
tracker migrate --from-beads               # One-time beads import
tracker stats                              # Vitals
```

Implementation: single Python file, ~300 lines, `click` or `typer` CLI wrapping the same SQLite functions the MCP server uses.

## 8. Migration from Beads

One-time migration script. Maps beads schema → new schema.

### Field mapping

| Beads column | New location |
|-------------|-------------|
| `id` | `id` (preserve original IDs) |
| `title` | `title` |
| `status` | `status` |
| `priority` | `priority` |
| `issue_type` | `type` |
| `description` | `description` |
| `notes` | `notes` |
| `assignee` | `assignee` |
| `created_at` | `created_at` |
| `updated_at` | `updated_at` |
| `closed_at` | `closed_at` |
| `design` | `fields.design` |
| `acceptance_criteria` | `fields.acceptance_criteria` |
| `estimated_minutes` | `fields.estimated_minutes` |
| `close_reason` | `fields.close_reason` |
| `mol_type`, `work_type`, etc. | `fields.*` (preserve as-is) |
| `deleted_at IS NOT NULL` | Skip (don't migrate deleted issues) |

### Dependency migration

```sql
-- Beads deps → new deps (straightforward, same structure)
INSERT INTO new.dependencies (issue_id, depends_on_id, type, created_at)
SELECT issue_id, depends_on_id, type, created_at
FROM beads.dependencies;
```

### Event migration

```sql
INSERT INTO new.events (issue_id, event_type, actor, old_value, new_value, comment, created_at)
SELECT issue_id, event_type, actor, old_value, new_value, comment, created_at
FROM beads.events;
```

### Label and comment migration

Direct copy — schemas are compatible.

## 9. File Structure

```
.beads_tree/
├── tracker.db               # SQLite database (single file)
├── tracker_mcp.py           # MCP server (~400 lines)
├── tracker_cli.py           # Thin CLI (~300 lines)
├── tracker_core.py          # Shared DB logic (~500 lines)
├── tracker_migrate.py       # One-time beads migration (~200 lines)
├── tracker_summary.py       # Summary generator (~200 lines)
├── agent-context.md         # Pre-computed summary (auto-generated)
├── beads_ui.py              # Web dashboard server
└── index.html               # Web dashboard frontend
```

Shared core: `tracker_core.py` contains all SQLite operations. Both MCP server and CLI import from it.

## 10. Implementation Order

1. **Core + schema** — `tracker_core.py` with SQLite setup, CRUD operations, dep management
2. **Templates** — built-in templates seeded on first run
3. **Summary generator** — `tracker_summary.py`, generates `agent-context.md`
4. **Thin CLI** — `tracker_cli.py` wrapping core
5. **Migration** — `tracker_migrate.py`, import 646 beads issues
6. **MCP server** — `tracker_mcp.py`, expose core as MCP tools
7. **Web dashboard** — `beads_ui.py` + `index.html` (the design from the companion doc)

## 11. What's Different from Beads

| Beads | New system |
|-------|-----------|
| 50+ typed columns | 10 core columns + JSON `fields` bag |
| Daemon + socket RPC | Direct SQLite (no daemon) |
| Git sync (beads-sync branch) | No sync — local file |
| JSONL as parallel format | SQLite only |
| `bd` CLI as primary interface | MCP primary, thin CLI secondary |
| Plans in markdown files | Plans as milestone→phase→step issue hierarchies |
| `bd prime` dumps text into context | Pre-computed summary file, one Read call |
| Generic issue fields | Typed templates (bug, requirement, milestone, phase, step) |
| content_hash, compaction, WAL export | Gone — not needed without sync |
