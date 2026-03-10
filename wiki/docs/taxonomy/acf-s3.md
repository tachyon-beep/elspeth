---
title: "ACF-S3: Structural Identity Spoofing"
---

# ACF-S3: Structural Identity Spoofing

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Spoofing |
| **Risk Rating** | Medium |
| **Existing Detection** | Partial |
| **Detection Feasibility** | AST-matchable |

## Description

A `hasattr()` check is used as a capability or privilege gate, allowing any object that declares the expected attribute to pass — regardless of whether the object is of the correct type. The gate accepts structural presence as proof of identity.

## Why Agents Produce This

`hasattr()` is the idiomatic Python pattern for duck-typing capability checks. Training data is saturated with it — agents building plugin systems, authorisation checks, or capability dispatchers will reach for `hasattr` by default because it is the "Pythonic" way to test whether an object supports an operation. The concept that structural presence is not ontological identity — that *having* an attribute is not the same as *being* the right type — is a security distinction that the language actively discourages.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — "Pythonic" duck-typing capability check
    def process_classified(obj):
        if hasattr(obj, "security_clearance"):
            handle_classified(obj)  # Any object with this attr gets in

    # Trivial bypass — no type hierarchy modification needed
    class Impersonator:
        security_clearance = "TOP_SECRET"  # Just declare the attribute

    process_classified(Impersonator())  # Gate opens

    # Worse — Python's __getattr__ protocol enables universal bypass:
    class UniversalImpersonator:
        def __getattr__(self, name):
            return True  # "Yes, I have that. And everything else."

    # This object passes EVERY hasattr check in the entire codebase.
    ```

=== "Correct"

    ```python
    # Correct — requires actual type membership
    def process_classified(obj):
        if isinstance(obj, ClearedPersonnel):
            handle_classified(obj)  # Must inherit from ClearedPersonnel
        # Cannot bypass without modifying the class hierarchy itself
    ```

## Why It's Dangerous

Unlike ACF-S1 (data fabrication via defaults) where the fabricated value is visible at the call site, the exploit surface for `hasattr` gates is anywhere an object is constructed — potentially far from the gate. The gate looks secure in isolation. This is the capability-based equivalent of ACF-S1's competence spoofing: ACF-S1 fabricates *data* where absence should be a failure; ACF-S3 fabricates *identity* where type membership should be required. The object claims to be something it isn't, and the gate believes it because the check is structural (has the attribute) rather than ontological (is the type). The elevation of privilege consequence follows directly — the impersonator passes through a privilege gate that should have rejected it.

## Detection Approach

An unconditional lint rule banning `hasattr()` catches all instances (the case study codebase enforces this). General-purpose linters do not flag `hasattr` because it is considered idiomatic Python. The semantic boundary enforcer treats `hasattr` as unconditionally prohibited — unlike `.get()` or `getattr()`, which are context-dependent, there is no legitimate use of `hasattr` that cannot be expressed more safely as `isinstance()`, explicit `try`/`except AttributeError`, or an allowset check. Detection is rated Partial because the rule is simple to implement but not present in any widely-deployed tool.

## Related Entries

- [ACF-S1: Competence Spoofing](acf-s1.md) — related spoofing pattern that fabricates data rather than identity
- [ACF-E1: Implicit Privilege Grant](acf-e1.md) — the elevation consequence of structural identity spoofing
- [How Threats Compound](../compounding-effect.md) — structural identity spoofing enables privilege escalation in the compounding scenario

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
