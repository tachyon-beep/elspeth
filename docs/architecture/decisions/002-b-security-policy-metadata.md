# ADR 002-B – Immutable Security Policy Metadata

## Status

Draft (2025-10-26)

## Context

ADR-002 established multi-level security (MLS) enforcement based on plugin
clearances and data classifications. ADR-005 introduced explicit downgrade
policy (`allow_downgrade`) to control whether a plugin can operate below its
clearance. During Phase 1 migrations we discovered that leaving downgrade policy
configurable by operators (via YAML/registry options) recreates the same silent
security gaps ADR-005 was meant to close. Operators could silently drop security
controls if policy metadata remained mutable at configuration time.

## Decision

Security policy metadata is treated as **immutable, author-owned, and signed**:

1. **Immutable Policy Fields** – `security_level`, `allow_downgrade`, and any
   future security policy fields (`max_operating_level`, etc.) are defined solely
   in code by the plugin author. Operators cannot override them via
   configuration, environment variables, or runtime hooks.
2. **Registry Enforcement** – Plugin registries reject registration schemas that
   expose policy fields. Factories must ignore/remove `allow_downgrade` (and
   similar) if supplied in configuration.
3. **Signature Attestation** – Published plugins include policy metadata in the
   signing manifest. Security review verifies the implementation matches the
   declared policy prior to signing.
4. **Frozen vs Trusted Downgrade** – Authors choose policy explicitly:
     - `allow_downgrade=True` → plugin trusted to downgrade (default for shipped
       plugins).
     - `allow_downgrade=False` → plugin frozen; MLS prevents operating below its
       clearance.
   The choice is hard-coded; operators select the appropriate plugin rather than
   modifying policy at runtime.
5. **Documentation & Tooling** – Developer guides, lint rules, and CI checks
   enforce that policy metadata is never exposed to configuration. Tests assert
   that registries ignore policy overrides.

## Consequences

- Prevents configuration-driven security downgrades (resolves the regression
  discovered in Phase 1).
- Guarantees that signing/attestation accurately reflects a plugin’s security
  posture for compliance and audit.
- Requires migrating legacy plugins to remove config-driven policy knobs and
  redeclare intent via constructor arguments.

## Related ADRs

- ADR-001 – Design Philosophy (Security-first)
- ADR-002 – Multi-Level Security Enforcement
- ADR-002-A – Trusted Container Model
- ADR-003 – Central Plugin Type Registry
- ADR-004 – Mandatory BasePlugin Inheritance
- ADR-005 – Frozen Plugin Capability

