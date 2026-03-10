---
title: "When This Does NOT Apply"
---

# When This Does NOT Apply

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

## Defensive programming is correct in most software

A web application that shows "Unknown" when a user's display name is missing is doing the right thing. Using `.get()` with sensible defaults is standard practice in most contexts. Graceful degradation is a virtue in the vast majority of software systems.

**This paper does NOT argue that all defensive coding is wrong.**

The patterns described in the [ACF taxonomy](taxonomy/index.md) — `.get()` with fabricated defaults, broad exception handlers that swallow errors, silent type coercion — are everyday best practices in web applications, CLI tools, data visualization, user-facing services, and most other software categories. In those contexts, a crash is worse than a reasonable default, and the guidance in this paper does not apply.

## This paper applies specifically when silent data corruption is worse than a crash

The failure modes catalogued here matter in systems where a confident wrong answer is worse than no answer at all. These include:

- **Audit trails and compliance records** — where every decision must be traceable to source data, and fabricated defaults are evidence tampering
- **Financial transaction processing** — where a silently defaulted value can misroute funds or misstate balances
- **Medical records and clinical decision support** — where a missing field defaulted to "normal" can suppress a critical alert
- **Identity and access management** — where a missing classification defaulted to the lowest tier silently downgrades access controls
- **Systems under regulatory accountability** — where complete traceability is a legal requirement, not a nice-to-have
- **Any system where "I don't know what happened" is not an acceptable answer** — where the ability to explain every output is a core requirement, not an aspirational goal

In these contexts, the correct response to missing or malformed data is to fail loudly and immediately — sometimes called "offensive programming" — because the system must never silently produce a result it cannot fully account for.

## The decision test

Ask this question about your system:

> **If a field is missing from a record, is it better for the system to crash, or to continue with a default value?**

If the answer is **"continue with a default"** — standard defensive programming applies, and most of this paper's concerns are irrelevant to your work. Your users are better served by graceful degradation than by crashes.

If the answer is **"crash — because a wrong answer is worse than no answer"** — you are in the territory this paper addresses. The patterns catalogued in the [ACF taxonomy](taxonomy/index.md) represent real risks to your system's integrity, and the detection and mitigation guidance applies.

Most systems contain a mix of both. A user-facing dashboard can show "N/A" for a missing metric. The audit record that feeds that dashboard cannot silently fabricate the metric's value.

## Even in applicable systems, not every function is security-critical

The trust tier model from the paper recognizes that different parts of a system operate at different trust levels. A utility function that formats a date string for display does not need the same scrutiny as a function that validates external input before writing to the audit trail.

The key boundaries where these failure modes are dangerous are:

- **External data ingestion** — where untrusted input enters the system
- **Audit trail writes** — where the permanent record is created
- **Trust tier transitions** — where data moves from one trust level to another
- **Decision points** — where data values determine routing, classification, or access

Code that operates entirely within a single trust tier, on already-validated data, with no audit implications, can use standard defensive patterns without concern.

[Read about the trust tier model →](paper.md#5-agent-output-as-a-trust-boundary)
