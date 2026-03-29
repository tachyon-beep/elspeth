# RC4.2 UX Remediation — Secret References Subplan

Date: 2026-03-30
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan covers assistant-safe secret references, dedicated secret entry UX,
and runtime secret resolution across user, org, and server scopes.

Included requirement:

- `REQ-API-02` — secret references

Primary surfaces:

- secret-resolution contract
- storage backends
- REST API
- composer tool exposure
- execution-time resolution
- settings/profile UX

---

## Goals

- Never expose plaintext secret values to the assistant or browser after
  submission.
- Let users see which secret references are available without seeing values.
- Resolve secrets server-side at use time via scoped lookup.

---

## Likely Decisions

- Contract-first design: protocol in shared layers, web backends on top.
- Write-only secret entry UX.
- User and server scopes first; org scope modelled for later rollout.

---

## Dependencies

- Runtime/config integration in execution.
- Auth/user identity plumbing for user-scoped lookup.

---

## Open Questions

- Exact server-secret inventory model and naming convention.
- Audit surface for resolved scope without leaking values.
- Whether org scope is planned now or explicitly deferred in the first full
  implementation.

---

## Expansion Notes

When expanded into a full plan, include:

- protocol and package layout
- storage model
- CRUD/inventory endpoints
- validation and execution integration
- UI rules for write-only handling
