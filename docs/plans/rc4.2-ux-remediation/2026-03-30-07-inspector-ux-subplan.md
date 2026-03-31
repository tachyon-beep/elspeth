# RC4.2 UX Remediation — Inspector UX Subplan

Date: 2026-03-30 (expanded 2026-03-31)
Status: Ready
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## 1. Scope

This subplan covers the three inspector-area UX enhancements from Wave 3:

- `REQ-UX-05` — version control restructure (compact selector, revert in
  dropdown)
- `REQ-UX-07` — graph readability improvements (larger nodes, fit button, edge
  labels, minimap)
- `REQ-UX-08` — plugin catalog panel (collapsible reference drawer)

Primary surfaces:

- `InspectorPanel.tsx` — header layout restructure
- `GraphView.tsx` — node sizing, layout, edge labels, minimap
- New `CatalogDrawer.tsx` — plugin reference drawer
- `Layout.tsx` — drawer overlay mechanism

Note: `REQ-UX-06` (validation status tint) is covered in sub-plan 05.

---

## 2. Goals

- Make the version control area compact and self-contained: version selector
  above the tabs, actions (validate, execute) adjacent, revert integrated into
  the version dropdown.
- Make the pipeline graph legible by default without manual zooming.
- Give users a browsable reference of available plugins without leaving the
  main workspace.

Non-goals:

- No interactive graph editing (drag-to-connect, add/remove nodes). The graph
  is a view, not an editor.
- No bidirectional spec-graph highlight sync (desirable follow-on, not in
  this wave).
- No plugin insertion from catalog panel (clicking to insert a chat
  suggestion is a design follow-on).

---

## 3. Architecture Decisions

### AD-1: Two-row inspector header (version row + tab row)

Current layout: a single header row with tabs on the left and version
dropdown + action buttons on the right, all at the same level.

New layout:

```
+----------------------------------------------+
|  v3 ▾  ● (tint)        [Validate] [Execute]  |  <- Row 1: version + actions
|  +------+-------+------+------+               |
|  | Spec | Graph | YAML | Runs |               |  <- Row 2: tabs
|  +------+-------+------+------+               |
+----------------------------------------------+
```

- Row 1: compact version selector (custom dropdown, not native `<select>`),
  validation tint dot (from sub-plan 05), Validate button, Execute button.
- Row 2: tab strip (unchanged ARIA structure).
- Revert action moves INTO the version dropdown: selecting an old version
  shows a "Revert to this version" button inside the dropdown.

### AD-2: Custom version dropdown replaces native `<select>`

The native `<select>` can't show a revert button or rich formatting (timestamp,
node count) per option. Replace with a custom dropdown:

- Trigger: compact button showing `v{N}` with a chevron.
- Panel: absolutely positioned below trigger, z-index above tab content.
- Each row: `v{N}` (bold) + node count + relative timestamp.
- Selected (non-current) row gets a "Revert" button inline.
- Click outside or Escape closes the panel.
- Keyboard: arrow keys navigate, Enter selects, Escape closes.

Lazy-load `stateVersions` on first open (existing `loadStateVersions()`
pattern, already wired to `onFocus`).

### AD-3: Graph node sizing and layout improvements

Current: `NODE_WIDTH = 180`, `NODE_HEIGHT = 50`, `nodesep = 40`,
`ranksep = 60`.

New values:

| Parameter | Old | New | Rationale |
|-----------|-----|-----|-----------|
| `NODE_WIDTH` | 180 | 260 | Fits plugin name + type badge + node ID comfortably |
| `NODE_HEIGHT` | 50 | 80 | Two-line content: plugin name (bold) + node type badge |
| `nodesep` | 40 | 60 | Prevents label overlap at larger node size |
| `ranksep` | 60 | 100 | Gives room for edge labels between ranks |

Node content (inside React Flow custom node):

```
+----------------------------+
|  [TRANSFORM]  classify     |  <- type badge + node ID
|  llm_transform             |  <- plugin name (muted)
+----------------------------+
```

### AD-4: `fitView` with explicit options for readability

Replace the bare `fitView` prop with `fitViewOptions`:

```tsx
fitViewOptions={{
  padding: 0.15,
  maxZoom: 1.5,
  minZoom: 0.3,
}}
```

This ensures the graph starts at a readable zoom level rather than shrinking
to fit everything into a tiny viewport. For large graphs, the user pans; the
minimap provides orientation.

### AD-5: Edge labels from edge_type

Map `edge_type` values to readable labels:

| `edge_type` | Label |
|-------------|-------|
| `on_success` | `success` |
| `on_error` | `error` |
| `route_true` | `true` |
| `route_false` | `false` |
| `fork` | `fork` |
| (other) | raw `edge_type` value |

Labels rendered via React Flow's `label` prop on edge objects, styled with
`fontSize: 10`, `fill: var(--color-text-muted)`. Error edges keep the existing
dashed animated style.

### AD-6: Minimap for graphs with >5 nodes

React Flow includes a built-in `<MiniMap>` component. Enable conditionally:

```tsx
{nodes.length > 5 && (
  <MiniMap
    nodeStrokeWidth={3}
    zoomable
    pannable
    style={{ bottom: 8, right: 8 }}
  />
)}
```

Position: bottom-right corner of the graph area.

### AD-7: Catalog panel as a slide-over drawer, not a grid column

The current layout is a strict 3-column grid (sidebar, chat, inspector). Adding
a fourth column would reduce chat/inspector width and complicate the resize
logic.

Instead: the catalog panel is a **slide-over drawer** that overlays the
inspector area from the right edge. When open, it covers the inspector content
but not the chat or sidebar.

Properties:

- `position: absolute` within the inspector grid cell (not `fixed` over the
  whole viewport -- the drawer belongs to the inspector area).
- Width: 320px (or the full inspector width if inspector is narrower).
- Height: 100% of the inspector area.
- Z-index: above tab content, below any modal dialogs.
- Backdrop: semi-transparent overlay over the inspector content.
- Toggle: a "Catalog" button in the inspector header (row 1, near the version
  selector) or a keyboard shortcut.
- Close: click backdrop, click X, or press Escape.

This approach:

- Requires no changes to `Layout.tsx` grid structure.
- Keeps the catalog contextually near the inspector.
- Doesn't steal space from chat.

### AD-8: Catalog data fetching and caching

The catalog is effectively static per server session (plugin list changes
require a server restart). Fetch on first open, cache indefinitely in
component-local state (no Zustand store needed).

Use the existing `client.ts` functions: `listSources()`, `listTransforms()`,
`listSinks()`, `getPluginSchema()`.

Fetch strategy:

1. On drawer open: fetch all three lists in parallel (`Promise.all`).
2. Cache the lists in component state.
3. On detail expand: fetch `getPluginSchema(type, name)` lazily.
4. Cache schema details per plugin name in a `Map`.

No `catalogStore.ts` needed -- the data is static and UI-local.

---

## 4. Detailed Changes

### Phase 7A: Version Control Restructure

#### 7A.1: Two-row header layout

File: `src/elspeth/web/frontend/src/components/inspector/InspectorPanel.tsx`

Replace the current single flex row (lines 124-285) with a two-row structure:

**Row 1 (version + actions):**

```tsx
<div style={{
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "6px 12px",
  borderBottom: "1px solid var(--color-border)",
}}>
  {/* Left: version selector + validation dot */}
  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
    <VersionSelector />
    <ValidationDot />  {/* from sub-plan 05 */}
  </div>
  {/* Right: action buttons */}
  <div style={{ display: "flex", gap: 6 }}>
    {/* Validate button (existing) */}
    {/* Execute button (existing) */}
  </div>
</div>
```

**Row 2 (tab strip):**

```tsx
<div style={{
  padding: "4px 12px 0",
  borderBottom: "1px solid var(--color-border)",
}}>
  <div role="tablist" aria-label="Inspector tabs" ...>
    {/* Same tab buttons as current */}
  </div>
</div>
```

#### 7A.2: `VersionSelector` component (new, inline in InspectorPanel)

Extract from InspectorPanel into its own component or an inline sub-component.

Props: none (reads from stores directly).

**Trigger button:** compact `v{N} chevron` button. Shows current version
number. `aria-expanded`, `aria-haspopup="listbox"`.

**Dropdown panel:** absolutely positioned below trigger.

- Each row: `v{N}` (bold) + `{node_count} nodes` (muted) + timestamp
- Non-current versions get an inline "Revert" button
- Revert fires `window.confirm()` then `revertToVersion(stateId)`
- Click-outside close via fixed backdrop at z-index one below the panel

**Keyboard support:**

- Escape closes the dropdown
- Arrow keys navigate version rows
- Enter activates the focused row's revert button
- Focus returns to trigger on close

**Lazy loading:** calls `loadStateVersions()` on first open (same as current
`onFocus` pattern).

---

### Phase 7B: Graph Readability

#### 7B.1: Update node sizing and layout constants

File: `src/elspeth/web/frontend/src/components/inspector/GraphView.tsx`
(lines 29-30, 38-67)

```tsx
const NODE_WIDTH = 260;   // was 180
const NODE_HEIGHT = 80;   // was 50

// In dagre config:
g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 100 });
//                           was 40       was 60
```

#### 7B.2: Richer node content

Replace the current single-line node label with a two-line layout showing
type badge + node ID on line 1, plugin name on line 2.

In the nodes array mapping (around line 83), replace the current `data.label`
with a structured JSX element:

- Line 1: type badge (small pill with `BADGE_BACKGROUNDS[type]` +
  `BADGE_COLORS[type]`, uppercase text, `fontSize: 10`) + node name/ID
  (`fontSize: 13, fontWeight: 600`)
- Line 2: plugin name in muted text (`fontSize: 11, color: var(--color-text-muted)`)

Node container style: `width: NODE_WIDTH`, `height: NODE_HEIGHT`,
`borderRadius: 8`, `border: 1px solid var(--color-border-strong)`,
`backgroundColor: var(--color-surface-elevated)`.

#### 7B.3: Edge labels

Add a label map constant:

```tsx
const EDGE_LABEL_MAP: Record<string, string> = {
  on_success: "success",
  on_error: "error",
  route_true: "true",
  route_false: "false",
  fork: "fork",
};
```

In the edges array mapping (around line 96), add:

```tsx
label: EDGE_LABEL_MAP[edge.edge_type] ?? edge.edge_type,
labelStyle: { fontSize: 10, fill: "var(--color-text-muted)" },
```

Error edges retain existing `animated: true` and error stroke colour.

#### 7B.4: fitView options

Replace bare `fitView` prop (line ~140) with:

```tsx
fitView
fitViewOptions={{ padding: 0.15, maxZoom: 1.5, minZoom: 0.3 }}
```

#### 7B.5: Minimap

After `<Controls showInteractive={false} />`, add:

```tsx
{rfNodes.length > 5 && (
  <MiniMap
    nodeStrokeWidth={3}
    zoomable
    pannable
    style={{ bottom: 8, right: 8, width: 120, height: 80 }}
  />
)}
```

Import: add `MiniMap` to the `@xyflow/react` import.

#### 7B.6: Verify fit button

The `<Controls>` component from React Flow includes a built-in fit-to-view
button. Verify it's visible and uses the `fitViewOptions`. If not, add a
standalone button. Try the built-in one first.

---

### Phase 7C: Plugin Catalog Panel

#### 7C.1: `CatalogDrawer` component (new file)

File: `src/elspeth/web/frontend/src/components/catalog/CatalogDrawer.tsx`

Props: `isOpen: boolean`, `onClose: () => void`.

Structure:

- **Backdrop** (position: absolute, inset: 0, semi-transparent, z-index: 30)
- **Drawer** (position: absolute, top/right/bottom: 0, width: 320px,
  z-index: 31)
  - Header: "Plugin Catalog" title + close button
  - Three tabs: Sources, Transforms, Sinks (role="tablist")
  - Scrollable plugin list per active tab
  - Each plugin renders via `PluginCard`

Data management:

- Fetch on first open: `Promise.all([listSources(), listTransforms(), listSinks()])`
- Cache in component state (no store)
- Schema details fetched lazily per plugin on expand
- Schema cache in a `Map<string, PluginSchemaInfo>` in component state

Keyboard: Escape closes drawer.

#### 7C.2: `PluginCard` component (new file)

File: `src/elspeth/web/frontend/src/components/catalog/PluginCard.tsx`

Props: `plugin: PluginSummary`, `schema: PluginSchemaInfo | null`,
`onExpand: () => void`.

Collapsible card:

- **Collapsed:** plugin name (bold, 13px) + one-line description (muted, 11px)
- **Expanded:** triggers `onExpand` (lazy schema fetch), then renders config
  field list from `schema.config_schema`:
  - Field name (bold)
  - Type (muted)
  - Required/optional badge
  - Description

#### 7C.3: Catalog toggle in InspectorPanel

In `InspectorPanel.tsx`:

- Add `const [catalogOpen, setCatalogOpen] = useState(false)` state.
- Add "Catalog" button in Row 1 of the header, before the Validate button.
- Render `<CatalogDrawer>` inside the inspector's outer container.
- Ensure the inspector's outer `<div>` has `position: "relative"` so the
  drawer's absolute positioning is scoped to it.

---

### Phase 7D: Tests

#### 7D.1: InspectorPanel tests

File: `src/elspeth/web/frontend/src/__tests__/InspectorPanel.test.tsx`

| Test | Expected |
|------|----------|
| `renders two-row header` | Version selector and action buttons in row 1, tabs in row 2 |
| `version selector shows current version` | Button text contains `v{N}` |
| `version dropdown opens on click` | Dropdown panel visible after click |
| `revert button appears for non-current version` | Revert button shown for historical version |
| `catalog button toggles drawer` | CatalogDrawer renders when button clicked |

#### 7D.2: GraphView tests

File: `src/elspeth/web/frontend/src/__tests__/GraphView.test.tsx`

| Test | Expected |
|------|----------|
| `renders nodes with correct dimensions` | Node style includes `width: 260` |
| `renders edge labels` | Edge elements contain label text |
| `shows minimap for >5 nodes` | MiniMap component renders |
| `hides minimap for <=5 nodes` | MiniMap not in DOM |
| `renders type badge and plugin name` | Node content includes type badge and plugin text |

#### 7D.3: CatalogDrawer tests

File: `src/elspeth/web/frontend/src/__tests__/CatalogDrawer.test.tsx`

| Test | Expected |
|------|----------|
| `renders nothing when closed` | No DOM output |
| `fetches catalog on first open` | API calls fired for sources, transforms, sinks |
| `shows three tabs` | Sources, Transforms, Sinks tabs visible |
| `switching tabs shows correct plugin list` | Tab content changes |
| `expanding plugin card fetches schema` | `getPluginSchema` called |
| `escape key closes drawer` | `onClose` called on Escape |
| `backdrop click closes drawer` | `onClose` called on backdrop click |

---

## 5. Implementation Order

```
Phase 7A (version restructure) ──────────────────────────────+
  7A.1  Two-row header layout                                 |
  7A.2  VersionSelector component                             |
                                                              |
Phase 7B (graph readability) -- independent of 7A ───────────+
  7B.1  Node sizing + layout constants                        |
  7B.2  Richer node content                                   |
  7B.3  Edge labels                                           |
  7B.4  fitView options                                       |
  7B.5  Minimap                                               |
  7B.6  Verify fit button                                     |
                                                              |
Phase 7C (catalog panel) -- independent of 7A/7B ────────────+
  7C.1  CatalogDrawer component                               |
  7C.2  PluginCard component                                  |
  7C.3  Catalog toggle in InspectorPanel                      |
                                                              |
Phase 7D (tests) -- after 7A + 7B + 7C ──────────────────────+
  7D.1  InspectorPanel tests
  7D.2  GraphView tests
  7D.3  CatalogDrawer tests
```

**Parallelism:** All three phases (7A, 7B, 7C) are fully independent and can
proceed in parallel. 7C depends on 7A only insofar as the catalog toggle
button placement depends on the new header layout -- but the drawer itself is
independent.

**Dependencies:**

- Sub-plan 05 should land first for the `ValidationDot` in the header (7A.1
  references it). If 05 hasn't landed, omit the dot placeholder -- it can be
  added when 05 merges.
- No backend changes in this sub-plan. All work is frontend-only.

**Estimated scope:** ~250 lines InspectorPanel restructure, ~100 lines
GraphView changes, ~250 lines CatalogDrawer + PluginCard, ~200 lines tests.
Two new files (CatalogDrawer.tsx, PluginCard.tsx). No backend changes.

---

## 6. Files Affected

### Modified

| File | Changes |
|------|---------|
| `src/elspeth/web/frontend/src/components/inspector/InspectorPanel.tsx` | Two-row header, VersionSelector, catalog toggle, drawer mount |
| `src/elspeth/web/frontend/src/components/inspector/GraphView.tsx` | Node sizing, layout config, edge labels, minimap, fitView options |

### New

| File | Purpose |
|------|---------|
| `src/elspeth/web/frontend/src/components/catalog/CatalogDrawer.tsx` | Slide-over drawer with tabbed plugin listing |
| `src/elspeth/web/frontend/src/components/catalog/PluginCard.tsx` | Collapsible plugin detail card |

### Possibly modified

| File | Condition |
|------|-----------|
| Theme CSS / tokens file | If `--color-accent` or other referenced variables don't exist |
| `src/elspeth/web/frontend/src/components/common/Layout.tsx` | Only if inspector outer div needs `position: relative` added |

---

## 7. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Custom dropdown accessibility | Medium | Implement full keyboard navigation (arrow keys, Escape, Enter), `aria-expanded`, `aria-haspopup`, focus management. Test with screen reader. |
| Larger graph nodes overflow small inspector panels | Low | `fitViewOptions` with `minZoom: 0.3` allows shrinking. Minimap aids orientation. Inspector is resizable (drag handle in Layout). |
| Catalog drawer covers inspector content | Low | By design -- it's a temporary overlay. Backdrop click and Escape close it immediately. The inspector content is still there underneath. |
| React Flow MiniMap dependency | Low | `<MiniMap>` is included in the `@xyflow/react` package already imported. No new dependency. |
| Plugin type mismatch between API and frontend | Low | The `PluginSummary.type` field uses `"source" | "transform" | "gate" | "sink"`. Gates are a subtype of transforms in the tab view. Map gates to the Transforms tab. |

---

## 8. Acceptance Criteria

### REQ-UX-05: Version Control Restructure

- [ ] Inspector header has two rows: version + actions on top, tabs below.
- [ ] Version selector is a compact `v{N}` button (not a native select).
- [ ] Version dropdown shows version number, node count, and timestamp per
      entry.
- [ ] Revert button appears inline in the dropdown for non-current versions.
- [ ] Keyboard navigation works in the dropdown (arrows, Enter, Escape).

### REQ-UX-07: Graph Readability

- [ ] Nodes are 260x80px with type badge and plugin name visible.
- [ ] Edge labels show readable connection types (success, error, true, false,
      fork).
- [ ] Graphs with >5 nodes show a minimap in the bottom-right corner.
- [ ] Default zoom level is readable without manual adjustment.
- [ ] Fit-to-view control is available and functional.

### REQ-UX-08: Plugin Catalog Panel

- [ ] "Catalog" button in inspector header opens a slide-over drawer.
- [ ] Drawer has three tabs: Sources, Transforms, Sinks.
- [ ] Each plugin shows name and one-line description.
- [ ] Expanding a plugin shows config schema details.
- [ ] Drawer closes on backdrop click, X button, or Escape.
- [ ] Catalog data is fetched once and cached.
