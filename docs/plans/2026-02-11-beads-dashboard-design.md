# Beads Dashboard — Design Specification

**Date:** 2026-02-11
**Status:** Draft (UX-reviewed)
**Purpose:** Read-only web UI for .beads issue tracker — understand project state at a glance without CLI queries.

## 1. Product Goal

A single-command local web dashboard that answers:
- "What's ready to work on?" (no blockers, ordered by priority)
- "What's blocking what?" (dependency graph)
- "What's the overall project shape?" (epic progress, status distribution)

Launch: `python .beads_tree/beads_ui.py` → opens browser at `localhost:8377`

## 2. Architecture

### Single Python File (`beads_ui.py`)

~150-200 lines. FastAPI with 4 endpoints:

| Endpoint | Returns |
|----------|---------|
| `GET /` | Serves `index.html` |
| `GET /api/issues` | All non-deleted issues with labels |
| `GET /api/dependencies` | All dependency edges |
| `GET /api/stats` | Counts by status, type, ready/blocked |

- Opens `beads.db` with `sqlite3` in read-only mode (`?mode=ro`)
- No ORM, no models — raw SQL, return dicts as JSON
- Auto-opens browser on startup via `webbrowser.open()`

### Single HTML File (`index.html`)

All JS/CSS from CDN, no build step:

| Library | Purpose | CDN |
|---------|---------|-----|
| Cytoscape.js | Dependency graph (pan, zoom, dagre layout) | unpkg |
| cytoscape-dagre | Hierarchical DAG layout plugin | unpkg |
| Tailwind CSS | Styling without CSS files | CDN play |
| (vanilla JS) | Kanban board, filtering, detail panel | — |

### Data Refresh

No polling, no websockets. Refresh on **visibility change**:

```js
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshData();
});
```

User alt-tabs to terminal, runs `bd` commands, alt-tabs back — dashboard refreshes automatically.

During refresh, a subtle "Refreshing..." indicator appears in the stats bar (typically <500ms for local SQLite).

### URL State

Hash-based routing preserves view state across refreshes:

```
localhost:8377/#graph
localhost:8377/#kanban
localhost:8377/#kanban-cluster
localhost:8377/#kanban&issue=elspeth-rapid-739
localhost:8377/#graph&issue=elspeth-rapid-739
```

## 3. Page Layout

```
┌──────────────────────────────────────────────────────────────┐
│ ◆ Beads    [Graph] [Kanban]    filter bar    Open:152 Ready:12│
├──────────────────────────────────────────────┬───────────────┤
│                                              │               │
│                                              │    Detail     │
│              Main View                       │    Panel      │
│     (graph or kanban, fills space)           │   (400px)     │
│                                              │               │
│                                              │               │
├──────────────────────────────────────────────┴───────────────┤
│ Open: 152 │ In Progress: 1 │ Ready: 12 │ Blocked: 38        │
└──────────────────────────────────────────────────────────────┘
```

- **Top nav:** Logo, view toggle tabs, filter bar, quick stats
- **Main area:** Active view fills available space
- **Detail panel:** Slides in from right (400px), overlays main content, doesn't shift layout
- **Stats bar:** Compact counts — always visible

## 4. Filter Bar

Shared across all views, same position in top nav:

```
┌──────────────────────────────────────────────────────────────────┐
│ [● Ready (12)] │ Priority [All ▼] │ 🔍 Search... │ Status [▼]   │
└──────────────────────────────────────────────────────────────────┘
```

**Priority order (most → least important):**

1. **Ready toggle** — ON by default. Highlights issues with zero open blockers. This is the primary signal.
2. **Priority dropdown** — All / P0-P1 / P2 / P3-P4. Filters cards and fades graph nodes.
3. **Text search** — Instant filter-as-you-type by title substring. Matching items highlight, non-matching fade.
4. **Status multi-select** — Open ✓, In Progress ✓, Closed ✗ by default. Toggle closed visibility.

**Filtering behavior:**
- In graph view: non-matching nodes **fade** (don't disappear) to preserve graph shape
- In kanban view: non-matching cards **hide** (simpler, columns reflow)

## 5. View 1: Dependency Graph

Full DAG visualization of all dependencies using Cytoscape.js + dagre layout.

### Two-Tier Graph Strategy

With 152+ open nodes, a flat dagre layout becomes unreadable. The graph has two modes:

**Tier 1: Epics Only (default)** — Shows only the synthetic root + 29 epic nodes + inter-epic dependencies. Immediately readable. Each epic node shows a child count badge.

**Tier 2: Epic Drill-Down** — Click an epic to expand it inline, revealing its children as a subgraph. Or use the "Show All" toggle to see everything (with the caveat that it'll be dense).

### Synthetic Root Node

A virtual "ELSPETH" node (not in DB) at the top of the graph:
- All 29 epics connect to it with dashed, thin "parent" edges
- Visually distinct: larger circle, project name label, not clickable for details
- Forces a single connected component so dagre produces a coherent layout
- Edges from root → epics styled differently (dashed, lighter) than real `blocks` dependencies (solid, darker)

### Node Visual Encoding

| Property | Encoding |
|----------|----------|
| **Type** | Shape: rounded-rect (task), hexagon (epic), diamond (bug), star (feature) |
| **Status** | Color: slate (closed), slate-blue (open), blue (in_progress) — see Color Palette below |
| **Ready** | Green left accent bar (4px) — consistent with kanban cards |
| **Priority** | Size: P0-P1 slightly larger than P3-P4 |
| **Label** | Truncated title (~30 chars) |

### Interactions

- **Click node** → detail panel slides in
- **Hover node** → tooltip: title, status, "blocks N / blocked by M"
- **Click edge** → highlights full dependency chain (upstream + downstream)
- **Pan/zoom** → built-in Cytoscape.js controls + zoom buttons [+] [-] [Fit] (bottom-right)
- **Auto-fit** → fits all visible nodes on load and after filter changes
- **`/` key** → focuses search bar (graph nodes highlight on match, non-matches fade)

### Dagre Configuration

```js
layout: {
  name: 'dagre',
  rankDir: 'TB',
  rankSep: 80,   // vertical space between ranks
  nodeSep: 40,   // horizontal space between nodes
  padding: 20
}
```

### Defaults

- **Epics-only mode** ON (manageable 29 nodes + root)
- Closed issues hidden
- Ready highlight ON — green accent nodes are visible immediately

## 6. View 2: Kanban Board

Three columns: **Open** | **In Progress** | **Closed**

Closed column collapsed by default (click header to expand — 493 cards would overwhelm).

### 6a. Standard Kanban

One card per issue.

**Card anatomy (96px height):**
```
┌─────────────────────────────────┐
│ 🐛 P1  Title of the issue...   │  ← type icon + priority badge + title
│ blocked by 2 🔗                 │  ← dependency info (if any)
├─────────────────────────────────┤  ← green left border if ready
```

- **Green left border (4px):** Issue is ready (no open blockers)
- **Red chain icon + count:** Issue is blocked
- **Type icon:** 🐛 bug, ✨ feature, 📋 task, 📊 epic
- **Priority badge:** Colored dot or label (P0 red, P1 orange, P2 neutral, P3-P4 faded)

**Sort order within columns:** Ready first → priority (P0 top) → creation date.

### 6b. Cluster Kanban

Toggle: `[Standard] [Cluster]` sub-tabs within the kanban view.

**Concept:** Epics absorb their children into a visual "deck of cards." The epic card covers its children, and the whole cluster moves as a unit.

**Epic cluster card (140px height):**
```
┌───────────────────────────────────────┐
│ 📊 Auth Refactor                 [14] │  ← type icon + title + child count
│ ████████▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░ │  ← segmented progress bar
│ 8 open · 4 in prog · 2 closed        │  ← text summary
├───────────────────────────────────────┤
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│  ← stacked peek (shadow/offset)
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
└───────────────────────────────────────┘
```

**Placement rule:** Cluster sits in the column matching the **epic's own status**.

**Progress bar segments:** Three colors matching status (amber open, blue in-progress, gray closed), proportional width.

**Interactions:**
- **Click epic** → accordion-expands children inline (pushes cards below down)
- Children sorted by: status → priority → creation date
- Child cards are indented 16px, use standard card design
- **Click chevron or click again** → collapse back to cluster
- Expanded state persists within session

**Orphan issues** (no parent epic) remain as standalone cards in their normal positions.

**Edge cases:**
- Epic closed but has open children → ⚠️ warning icon on cluster card
- Epic open but all children closed → ✓ completion indicator

**Column card counts:**
- Standard mode: ~152 cards in Open
- Cluster mode: ~29 clusters + orphans — dramatically more scannable

## 7. Detail Panel

Slides in from right edge (400px wide). Opened by clicking any card or graph node.

### Header
- Issue ID (`elspeth-rapid-739`) + type icon
- Full title (untruncated)
- Status badge + priority badge
- Ready indicator ("Ready — no blockers") or blocked indicator

### Body (scrollable)
- **Description** — full text, basic markdown rendered
- **Dependencies:**
  - "Blocks →" list with status badges per issue
  - "Blocked by ←" list with status badges (red if blocker is still open)
- **Notes** — if present
- **Design** — if present
- **Timeline** — recent events from `events` table (status changes, creation). Compact, most-recent-first.

### Footer
- Copyable CLI command: `bd show elspeth-rapid-739`

### Behavior
- **Close:** Escape key or click outside panel
- **Navigate:** Clicking a dependency link in the panel opens that issue (swaps panel content + highlights in graph)
- **Persist:** Selected issue ID stored in URL hash — survives alt-tab refresh

## 8. Visual Design

### Color Palette (UX-reviewed)

**Key decision:** Status uses cool tones (blues/grays), priority uses warm tones (reds/oranges). This eliminates the amber-open vs orange-P1 conflict flagged in UX review.

**Status colors (primary encoding — cool channel):**
| Status | Color | Hex | Usage |
|--------|-------|-----|-------|
| Open | Slate blue | `#64748B` | Node fill, card accent, badge |
| In Progress | Blue | `#3B82F6` | Node fill, card accent, badge |
| Closed | Gray | `#9CA3AF` | Node fill, card accent, badge |

**Priority colors (secondary encoding — warm channel):**
| Priority | Color | Hex | Usage |
|----------|-------|-----|-------|
| P0 | Red | `#EF4444` | Dot/badge |
| P1 | Orange | `#F97316` | Dot/badge |
| P2 | Gray | `#6B7280` | No special indicator |
| P3-P4 | Light gray | `#D1D5DB` | Faded/muted |

**Signal colors (overlays):**
| Signal | Color | Hex | Usage |
|--------|-------|-----|-------|
| Ready | Emerald | `#10B981` | Left border 4px (kanban), accent bar (graph) |
| Blocked | Red | `#EF4444` | Chain icon, blocker badges in detail panel |

### Typography
- **Font:** Monospace (`JetBrains Mono`, `Fira Code`, `monospace`) — dev-tool aesthetic
- **Card title:** 14px (`text-sm`), medium weight, tight line-height (1.4)
- **Card meta:** 12px (`text-xs`), regular weight, `text-gray-400`
- **Graph labels:** 11px
- **Detail heading:** 18px (`text-lg`), semibold
- **Body text (detail panel):** 14px, line-height 1.6

### Spacing
- Card padding: 12px (compact but breathable)
- Card gap: 8px vertical (dense stacking)
- Filter bar gap: 12px between controls
- Detail panel padding: 20px

### Theme — Dark Only (V1)
```css
body { background: #0F172A; color: #F1F5F9; }  /* slate-900 bg, slate-100 text */
```
- Dark background (`#0F172A`), lighter card surfaces (`#1E293B`)
- High contrast text (`#F1F5F9`) on dark backgrounds
- Focus indicators: `outline: 2px solid #3B82F6; outline-offset: 2px;`

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `/` | Focus search bar |
| `Escape` | Close detail panel / clear search |
| `Enter` | Open detail panel for focused card/node |
| Arrow keys | Navigate cards (kanban) / nodes (graph) |

## 9. Data Model (API Responses)

### `GET /api/issues`
```json
[
  {
    "id": "elspeth-rapid-739",
    "title": "Double Token Outcome Recording Test",
    "status": "closed",
    "priority": 2,
    "issue_type": "task",
    "assignee": "",
    "created_at": "2026-01-30T03:30:00",
    "closed_at": "2026-01-31T12:00:00",
    "description": "...",
    "notes": "...",
    "design": "...",
    "labels": ["engine", "tests"],
    "parent_epic": "elspeth-rapid-t12",
    "blocks": ["elspeth-rapid-f5t"],
    "blocked_by": ["elspeth-rapid-t12"],
    "is_ready": false
  }
]
```

### `GET /api/dependencies`
```json
[
  {
    "from": "elspeth-rapid-3oe",
    "to": "elspeth-rapid-t12",
    "type": "blocks"
  }
]
```

### `GET /api/stats`
```json
{
  "by_status": {"open": 152, "in_progress": 1, "closed": 493},
  "by_type": {"task": 285, "bug": 306, "epic": 29, "feature": 26},
  "ready_count": 12,
  "blocked_count": 38,
  "total_dependencies": 423
}
```

## 10. File Structure

```
.beads_tree/
├── beads_ui.py          # FastAPI server (~200 lines)
├── index.html           # Single HTML file with embedded JS (~800-1000 lines)
└── README.md            # Launch instructions (optional)
```

No `node_modules`, no `package.json`, no build step. Two files that do everything.

## 11. Implementation Order

1. **Python server** — FastAPI, SQLite queries, serve HTML, auto-open browser
2. **HTML skeleton** — layout, nav, filter bar, dark theme, Tailwind CDN
3. **Kanban standard** — columns, cards, sorting, click → detail panel
4. **Kanban cluster** — epic grouping, progress bars, accordion expand
5. **Dependency graph** — Cytoscape.js, dagre layout, synthetic root, node styling
6. **Filtering** — ready highlight, priority, search, status
7. **Detail panel** — slide-in, issue details, dependency navigation
8. **Polish** — visibility-change refresh, URL hash state, keyboard shortcuts (Escape to close)
