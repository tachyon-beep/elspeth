# RC4.2 UX Remediation — Inspector UX Subplan

Date: 2026-03-30
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan groups the right-hand authoring/inspection experience changes that
share layout and navigation concerns.

Included requirements:

- `REQ-UX-05` — version control restructure
- `REQ-UX-07` — graph readability improvements
- `REQ-UX-08` — plugin catalog panel

Primary surfaces:

- inspector layout and navigation
- graph presentation
- catalog browsing UI

---

## Goals

- Make version/context controls easier to understand.
- Make the graph readable enough to be useful by default.
- Give users a discoverable view of available sources, transforms, and sinks.

---

## Likely Decisions

- Put version control in a compact parent control above content tabs.
- Treat graph as a view first, not an editor.
- Consider a shared drawer pattern for catalog and related reference surfaces.

---

## Dependencies

- Validation UX work may influence final placement of version status indicators.
- Blob manager drawer decisions may affect catalog-panel placement.

---

## Open Questions

- Whether catalog and blobs should share a drawer or remain separate panels.
- Whether graph follow-ons like edge labels and minimap should land in the same
  pass as readability fixes.
- How much version history detail belongs in the compact selector.

---

## Expansion Notes

When expanded into a full plan, include:

- layout sketches
- tab/control hierarchy
- graph rendering constraints
- catalog data-fetching and caching approach
