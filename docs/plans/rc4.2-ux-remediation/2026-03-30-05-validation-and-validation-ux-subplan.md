# RC4.2 UX Remediation — Validation And Validation UX Subplan

Date: 2026-03-30
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan covers richer Stage 1 validation output plus the lightweight UI
affordances that surface validation state in the inspector.

Included requirements:

- `REQ-API-07` — enhanced validation model
- `REQ-UX-06` — validation status tint

Primary surfaces:

- composition-time validation summary
- tool result serialization
- transient frontend validation state
- inspector status display

---

## Goals

- Distinguish blocking errors from advisory warnings and optional suggestions.
- Make validation state visible without forcing users to open a dedicated
  validate panel every time.

---

## Likely Decisions

- Keep warnings/suggestions Stage 1 only in the initial rollout.
- Decide explicitly whether warnings/suggestions are transient or persisted.
- Attach the ambient validation signal to the version-control area.

---

## Dependencies

- Inspector layout changes may affect final placement of the status indicator.

---

## Open Questions

- Whether warnings/suggestions should persist in stored composition state or
  stay transient from the latest mutation response.
- Which initial warning/suggestion rules provide the most value without noise.

---

## Expansion Notes

When expanded into a full plan, include:

- validation data model
- response serialization changes
- frontend state ownership
- inspector rendering rules
