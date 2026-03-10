---
title: "ACF-T1: Trust Tier Conflation"
---

# ACF-T1: Trust Tier Conflation

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Tampering |
| **Risk Rating** | Critical |
| **Existing Detection** | None |
| **Detection Feasibility** | Taint-required |

## Description

Data from an external (untrusted) source is used in an internal (trusted) context without passing through a validation boundary. The data's effective trust level is silently elevated.

## Why Agents Produce This

Python's type system doesn't distinguish between data from different sources. A `dict` from `requests.get().json()` and a `dict` from a validated internal query are the same type. Agents see both as "a dict" and treat them interchangeably because nothing in the language tells them otherwise.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — clean, readable, catastrophically wrong
    def sync_partner_records(partner_api_url):
        response = requests.get(f"{partner_api_url}/records")
        records = response.json()
        for record in records:
            db.execute(
                insert(internal_records).values(**record)
            )
        # External data inserted directly into internal database.
        # No schema validation, no field allowlisting, no type checking.
        # Partner could send arbitrary fields, wrong types, injection payloads.
    ```

=== "Correct"

    ```python
    # Correct — validate at the boundary
    def sync_partner_records(partner_api_url):
        response = requests.get(f"{partner_api_url}/records")
        raw_records = response.json()
        for raw in raw_records:
            try:
                validated = PartnerRecordSchema.validate(raw)
            except ValidationError as e:
                quarantine(raw, reason=str(e))
                continue
            db.execute(
                insert(internal_records).values(
                    name=validated.name,
                    status=validated.status,
                )
            )
    ```

## Why It's Dangerous

This is the most critical failure mode because it compromises the integrity of the internal data store — the system's source of truth. Once external data enters the internal store without validation, every downstream consumer trusts it as internal data. Corruption propagates invisibly.

## Detection Approach

Taint analysis — trace the return values of functions marked `@external_boundary` (or matched by the known external call heuristic list) and flag if they reach data store operations without passing through a function marked `@validates_external`. This is the core capability of the tool described in Appendix B of the paper.

## Related Entries

- [ACF-T2: Silent Coercion](acf-t2.md) — related tampering pattern involving type coercion across boundaries
- [ACF-E1: Implicit Privilege Grant](acf-e1.md) — the elevation consequence of trust tier conflation
- [How Threats Compound](../compounding-effect.md) — trust tier conflation is step 1 in the 5-step compounding scenario

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
