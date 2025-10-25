# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records documenting significant architectural and design decisions for Elspeth.

## What are ADRs?

Architecture Decision Records capture important architectural decisions along with their context and consequences. They provide a historical record of why certain design choices were made, helping current and future team members understand the reasoning behind the system's architecture.

## Active ADRs

These decisions are currently in effect and guide ongoing development:

| ADR | Title | Date | Status | Summary |
|-----|-------|------|--------|---------|
| [001](001-design-philosophy.md) | Design Philosophy | 2025-10-23 | ✅ Accepted | Establishes security-first priority hierarchy: Security → Data Integrity → Availability → Usability |
| [002](002-security-architecture.md) | Multi-Level Security Enforcement | 2025-10-23 | ✅ Accepted | Implements Bell-LaPadula MLS model with pipeline-wide minimum evaluation for fail-fast security |
| [002-A](002-a-trusted-container-model.md) | Trusted Container Model | 2025-10-25 | ✅ Accepted | Introduces ClassifiedDataFrame for immutable classification tracking and high water mark enforcement |
| [003](003-plugin-type-registry.md) | Central Plugin Type Registry | 2025-10-25 | 📋 Proposed | Central registry for plugin security validation with type-safe plugin composition |
| [004](004-mandatory-baseplugin-inheritance.md) | Mandatory BasePlugin Inheritance | 2025-10-25 | 📋 Proposed | Requires all plugins to inherit from BasePlugin for security enforcement |
| [005](005-security-critical-exception-policy.md) | Security-Critical Exception Policy | 2025-10-25 | 📋 Proposed | Policy-enforced fail-loud exceptions for security invariant violations |

## Historical ADRs

These decisions have been completed or superseded but remain documented for historical context:

| ADR | Title | Status | Summary |
|-----|-------|--------|---------|
| [003](historical/003-remove-legacy-code.md) | Remove Legacy Code | Completed | Removed duplicate orchestration helpers after new pipeline achieved feature parity |
| [004](historical/004-complete-registry-migration.md) | Complete Registry Migration | Completed | Migrated all plugin registries to unified `BasePluginRegistry` framework |

## ADR Format

We follow the lightweight [Michael Nygard ADR format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) with structured sections for clarity. See **[000-template.md](000-template.md)** for the complete template with detailed guidance.

**Core structure:**

- **Status**: Current state (Proposed, Accepted, Deprecated, Superseded) with date
- **Context**: Problem statement and background
- **Decision**: What we decided, with specific numbered points and code examples
- **Consequences**: Benefits, Limitations/Trade-offs, and Implementation Impact
- **Related Documents**: Links to related ADRs, architecture docs, and implementation files

## Creating a New ADR

1. **Determine the next number**: Check the highest numbered ADR in this directory
2. **Copy the template**: `cp 000-template.md XXX-short-title.md`
3. **Fill in the sections**:
   - **Context**: Why is this decision needed? What's the problem? What alternatives were considered?
   - **Decision**: What are we going to do? Be specific with numbered points and code examples.
   - **Consequences**: Break down into Benefits, Limitations/Trade-offs (with mitigations), and Implementation Impact
   - **Related Documents**: Link to related ADRs and implementation files
4. **Start with Status: Proposed** for review
5. **Create a PR** and discuss with the team
6. **Update to Status: Accepted** once approved and merged
7. **Add metadata**: Include Last Updated date and Author(s) at the bottom

## ADR Lifecycle

- **Proposed**: Draft under review
- **Accepted**: Approved and in effect
- **Deprecated**: No longer recommended but not replaced
- **Superseded**: Replaced by a newer ADR (link to the new one)

When an ADR is superseded or becomes historical, move it to the `historical/` subdirectory and update this README.

## Principles for Good ADRs

- **Capture context**: Future readers won't have the same context you do today
- **Be specific**: Vague decisions lead to inconsistent implementations
- **Document trade-offs**: Honest assessment of limitations helps future decision-makers
- **Link to related docs**: Create a documentation graph for easy navigation
- **Keep it concise**: Aim for 1-2 pages; link to detailed specs if needed
- **Use code examples**: Show, don't just tell (especially for technical decisions)

## Related Documentation

- **[../security-controls.md](../security-controls.md)** – Security control implementation details
- **[../plugin-security-model.md](../plugin-security-model.md)** – Plugin security architecture
- **[../threat-surfaces.md](../threat-surfaces.md)** – Attack surface analysis
- **[../../development/contributing.md](../../development/contributing.md)** – Contribution guidelines

---

**Last Updated**: 2025-10-25
**Maintained By**: Architecture Team
