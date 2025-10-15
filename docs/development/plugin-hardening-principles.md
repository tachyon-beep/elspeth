# Plugin Hardening Principles & Roadmap

This note captures the long-term plugin architecture reforms originally outlined in the external `PLUGIN_REFORM.md`. It complements the feature roadmap by describing how we intend to make plugins safer, more discoverable, and easier to audit.

## North Star Principles

1. **Secure by default** – least privilege, deny-by-default policies, and safe configuration defaults.
2. **Self-describing plugins** – every plugin publishes a manifest that states its capabilities, inputs, outputs, and requirements.
3. **Isolation tiers** – trusted core plugins run in-process, while vetted or third-party plugins execute out-of-process with strict Host API boundaries.
4. **Policy as code** – classification, egress, and secret access rules enforced centrally instead of ad-hoc checks.
5. **Great developer experience** – discovery, scaffolding, and validation happen via the CLI so contributors cannot accidentally ship unsafe code.

## Key Initiatives

### 1. Plugin Manifest

- Require `PluginManifest` metadata (name, type, version, API compatibility, schemas, required permissions, classification bounds, egress allow-lists).
- Validate manifests at load time and refuse incompatible API versions.
- Expose manifest information via `elspeth plugins info` for operators and auditors.

### 2. Capability-Based Host API

- Provide plugins with a narrow Host API (`open_output`, `http_request`, `emit_metric`) that enforces path sandboxing, TLS, hostname allow-lists, timeouts, and classification gates.
- Block direct environment and filesystem access for untrusted plugins; all privileged actions go through the Host API.

### 3. Trust Tiers & Execution Modes

- **Core** plugins: code reviewed, run in-process.
- **Vetted** plugins: run out-of-process with a thin RPC boundary and minimal environment.
- **Untrusted** plugins: executed in containers or micro-VMs with seccomp/AppArmor, cgroup limits, read-only root, and controlled egress.

### 4. Policy Engine Integration

- Centralise classification, egress, and secret policies using a ruleset (initially Python + JSON Schema; future OPA/Cedar integration).
- Deny execution if an experiment’s security level exceeds a plugin’s declared maximum or if egress targets are disallowed.

### 5. Supply Chain Integrity

- Sign plugin distributions (e.g., Sigstore), pin dependencies with hashes, generate SBOMs, and run vulnerability scanners in CI.
- Maintain an allow-list of plugin package names and record attestation data per run.

### 6. Versioning & Compatibility

- Establish a clear semver for the plugin SDK.
- Require plugins to declare `api_version`; refuse to load incompatible plugins and provide compatibility adapters where practical.
- Add `elspeth plugins doctor` to warn about version drift.

### 7. Observability & Resilience

- Bake in timeouts, retries with jitter, circuit breakers, and concurrency limits.
- Emit OpenTelemetry traces and structured logs (no secrets) with per-plugin SLIs for latency and error rates.
- Use idempotency keys/outbox patterns so output retries do not duplicate work.

### 8. Developer Experience

- CLI improvements: `elspeth plugins ls/info/verify/plan`.
- Scaffold generator `elspeth plugin init` that writes manifests, stubs, and tests.
- Static validation that fails builds when plugins request unapproved permissions or lack rationale.

## Middleware Reform Highlights

- Separate **LLM clients** (transport/auth/retries) from **middleware** (policy, safety, auditing, routing).
- Define middleware lifecycle hooks (`on_request`, `on_stream_delta`, `on_response`, `on_error`) with deterministic ordering and label selectors.
- Support selectors that match on client tags (e.g., provider, capability) instead of hard-coded vendor checks.
- Offer guardrail services as pluggable sidecars or remote services, with circuit breakers and fail-open/fail-closed policies by classification.

## Router Sink Pattern

To improve post-processing, introduce a router sink:

- Evaluates JSONLogic-style criteria to route rows to child sinks.
- Enforces classification gates, egress allow-lists, and schema projections per route.
- Produces a signed routing manifest for auditability and retry safety.

## Migration Approach

1. Introduce manifests and Host API behind feature flags; migrate core plugins first.
2. Implement CLI discovery/verification commands.
3. Enable Excel/CSV sanitisation by default (completed WP1).
4. Roll out out-of-process execution for vetted/untrusted plugins.
5. Layer in supply-chain controls (signed packages, SBOM, scanners).
6. Integrate policy engine and OpenTelemetry instrumentation.

These principles remain active and are referenced by the feature roadmap. Update this note as we deliver each initiative, and mirror status in `../roadmap/FEATURE_ROADMAP.md`.
