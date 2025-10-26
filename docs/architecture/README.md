# Architecture Documentation

This directory contains the technical architecture documentation for Elspeth's core design patterns, plugin system, and data flows.

## Core Architecture

- **[architecture-overview.md](architecture-overview.md)** – High-level system architecture and component interactions
- **[component-diagram.md](component-diagram.md)** – Visual component diagram with current plugin paths (updated Oct 2025)
- **[data-flow-diagrams.md](data-flow-diagrams.md)** – Data flow patterns through the orchestration pipeline

## Plugin System

- **[plugin-catalogue.md](plugin-catalogue.md)** – Complete catalogue of all datasources, LLMs, middleware, sinks, and experiment plugins
- **[plugin-security-model.md](plugin-security-model.md)** – Security context propagation and plugin isolation
- **[../development/plugin-authoring.md](../development/plugin-authoring.md)** – How to build, register, secure, and test plugins
- **[configuration-security.md](configuration-security.md)** – Validation pipeline, secret handling, and merge semantics (defaults → packs → experiments)

## LLM Integration

- **[middleware-lifecycle.md](middleware-lifecycle.md)** – Comprehensive middleware lifecycle documentation (Oct 2025)
- **[llm-tracing-plugin-options.md](llm-tracing-plugin-options.md)** – LLM tracing and observability patterns
- **[embeddings-rag-plugin-design.md](embeddings-rag-plugin-design.md)** – RAG and embeddings store design

## Security & Audit

- **[security-controls.md](security-controls.md)** – Security control inventory and implementation
- **[threat-surfaces.md](threat-surfaces.md)** – Identified attack surfaces and mitigations
- **[audit-logging.md](audit-logging.md)** – Audit logging architecture and patterns

## Architecture Decisions

- **[decisions/](decisions/)** – Architecture Decision Records (ADRs) documenting key design and security decisions
  - [ADR-001: Design Philosophy](decisions/001-design-philosophy.md) – Security-first priority hierarchy governing all architectural decisions
  - [ADR-002: Multi-Level Security Enforcement](decisions/002-security-architecture.md) – Bell-LaPadula MLS model with pipeline-wide minimum evaluation

### Verification (Signing & SBOM)

All published container images are signed with Sigstore Cosign and include a CycloneDX SBOM attestation. Verification options:

- Keyless (GitHub OIDC):
  - `cosign verify --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity-regexp "https://github.com/OWNER/REPO/.*" ghcr.io/OWNER/REPO:TAG`
- Internal KMS/key (if configured):
  - `cosign verify --key awskms://arn:aws:kms:... ghcr.io/OWNER/REPO:TAG`
- SBOM attestation (CycloneDX):
  - `cosign verify-attestation --type cyclonedx ghcr.io/OWNER/REPO:TAG | jq`

The CI workflow treats both signing and attestation as mandatory gates. During migration, you may dual‑sign (keyless + internal) and later restrict admission to internal signatures only.

## Related Documentation

### Compliance & Governance

For compliance controls, accreditation, and security audits, see [`../compliance/`](../compliance/)

### Development Practices

For testing, logging standards, and upgrade strategies, see [`../development/`](../development/)

### Future Work

For roadmap and completed refactoring initiatives, see [`../roadmap/`](../roadmap/)

---

**Audience:** Technical architects, platform developers, and plugin authors.

**Last Updated:** 23/10/25
