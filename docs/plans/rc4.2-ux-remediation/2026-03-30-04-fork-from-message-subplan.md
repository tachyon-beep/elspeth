# RC4.2 UX Remediation — Fork From Message Subplan

Date: 2026-03-30
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan covers editing a prior user message and creating a new session fork
from that point, with preserved provenance and inherited composition state.

Included requirement:

- `REQ-UX-03` — chat bubble edit and fork from here

Primary surfaces:

- session/message persistence
- composition-state provenance
- fork API
- chat/session frontend UX

---

## Goals

- Let users branch from an earlier point without mutating history.
- Preserve the original session as a complete, auditable timeline.
- Make the forked session clearly identifiable in the UI.
- Ensure forked state reflects the selected historical point, not the latest
  session state.

---

## Likely Decisions

- Add explicit state provenance to messages.
- Treat forking as session creation with inherited context, not rollback.
- Keep provenance visible in the forked session header or metadata area.

---

## Dependencies

- Blob-manager decisions, if forked sessions must also inherit input/output
  blobs cleanly.

---

## Open Questions

- Exact fork payload and response shape.
- How much inherited chat history should be duplicated into the fork.
- Whether the forked session should surface a synthetic "forked from" message in
  the transcript in addition to header metadata.

---

## Expansion Notes

When expanded into a full plan, include:

- schema changes for provenance
- service-layer duplication rules
- blob inheritance behavior
- user-visible fork navigation flow
