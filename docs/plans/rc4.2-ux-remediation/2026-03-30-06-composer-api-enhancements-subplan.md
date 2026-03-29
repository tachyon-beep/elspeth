# RC4.2 UX Remediation — Composer API Enhancements Subplan

Date: 2026-03-30
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan groups the assistant/composer authoring API improvements that make
iterative pipeline editing cheaper and more expressive.

Included requirements:

- `REQ-API-03` — patch operations
- `REQ-API-04` — atomic full pipeline replacement
- `REQ-API-05` — clear source
- `REQ-API-08` — explain validation errors
- `REQ-API-09` — list models

Primary surfaces:

- `CompositionState`
- composer tools and tool result shapes
- catalog/model discovery

---

## Goals

- Reduce needless full-object rewrites by the assistant.
- Support atomic first-pass pipeline creation.
- Improve self-repair loops through richer discovery and explanation tools.

---

## Likely Decisions

- Use JSON merge-patch for partial option updates.
- Keep `set_pipeline` atomic and versioned as a single state change.
- Treat model listing and validation explanation as discovery aids, not direct
  execution features.

---

## Dependencies

- Validation model decisions, especially for response shape consistency.

---

## Open Questions

- Whether `set_pipeline` should fully replace metadata/source/nodes/edges/outputs
  or support partial omission semantics.
- How much provider/model information should be dynamic versus curated.

---

## Expansion Notes

When expanded into a full plan, include:

- state mutation API design
- tool definitions and payload shapes
- validation/error semantics
- backwards-compatibility considerations
