# RC4.2 UX Remediation — Blob Manager Subplan

Date: 2026-03-30
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan covers the new blob/file-management subsystem for user inputs and
pipeline outputs.

Included requirement:

- `REQ-API-01` — blob manager

Primary surfaces:

- blob persistence and storage
- REST API
- composer tools
- execution integration
- blob manager UI

---

## Goals

- Let users upload, browse, download, and reuse files without handling raw
  filesystem paths.
- Map blobs cleanly to chat inputs, job inputs, job outputs, and downloadable
  artifacts.
- Preserve a clear boundary between user-facing blob objects and audit-facing
  payload storage.

---

## Likely Decisions

- Session-scoped blobs with explicit run/job linkage.
- Internal path resolution via blob references, not user-provided paths.
- Copy-on-fork if forked sessions must inherit blob-backed state.

---

## Dependencies

- Execution integration for output blobs.
- Forking decisions if blobs must survive or copy across session forks.

---

## Open Questions

- Blob metadata shape for schema inference and run linkage.
- Exact UX for "use as input" from the file manager.
- How aggressively to phase schema inference, output wiring, and drag/drop.

---

## Expansion Notes

When expanded into a full plan, include:

- DB schema
- storage layout and lifecycle rules
- IDOR/ownership enforcement
- execution hooks
- frontend drawer interaction model
