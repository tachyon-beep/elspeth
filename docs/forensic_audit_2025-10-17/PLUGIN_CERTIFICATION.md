# Accountability-preserving model

Here’s a pattern that keeps the blast-radius small **without** taking accountability away from plugin owners.

1. **Signed intent (declaration)**

   * Each plugin ships a signed manifest stating its **capabilities**: e.g. endpoints it may call, data classes it may touch, external SDKs it may use, resource limits.
   * Think of it as a *capability covenant*. The plugin owner authors and signs it; the CISO/CTO certifies it.

2. **Build provenance**

   * Reproducible build; signed artifact; attach SBOM. Record build pipeline identity (SLSA-style provenance).
   * The platform **verifies signatures and hashes at load** and stamps a run with the exact artifact digest.

3. **Run-time identity + observation (not enforcement)**

   * The platform tags every call path and log with **plugin_id + artifact_digest**.
   * Optional lightweight wrappers only **record**: destination host, scheme, DNS result, timeouts, payload class (not contents), latency.
     Crucially: they **don’t widen permissions or “correct” the plugin**; they just produce tamper-evident telemetry.

4. **Conformance audit**

   * A background auditor compares **observed behaviour** to the **declared capability covenant**:

     * “Plugin A declared it would only call `*.openai.azure.com`; last run showed `api.randomsite.com`: non-conforming.”
   * Breaches trigger:

     * **Alert** to plugin owner + security.
     * **Auto-quarantine** option (kill-switch) based on policy.
     * Evidence bundle for incident review.

5. **Revocation & kill switch**

   * Maintain a revocation list (CRL) of artifact digests.
   * If a plugin steps out of bounds, **revoke its digest**; the platform refuses to load it until the owner ships a remediated, re-signed version.

This keeps the platform’s job to **verify, attribute, and revoke**, while the **plugin owner remains fully accountable** for allowed egress, data handling, and correctness.

# Where (limited) central controls still help without stealing ownership

* **Isolation for blast-radius**: run plugins in a separate process/container with minimal privileges. That’s not “fixing” their policy; it’s **containing** their mistakes.
* **Observation-only egress mirror**: route via a corporate proxy/egress gateway that exports logs keyed by plugin identity. Default action is **allow**, but with perfect attribution. Security can flip to **deny** only when policy says so (e.g., after a breach).
* **Fail-closed on *absence* of signatures**: refuse to execute if the plugin isn’t signed or the manifest is missing. That’s about provenance, not policing content.

# Certification checklist (owner responsibilities)

* **Manifest** declares:

  * Approved egress domains (wildcards allowed but anchored), schemes, ports.
  * Data classifications processed; retention & redaction strategy.
  * External SDKs and versions.
* **Tests**:

  * Positive/negative egress tests proving enforcement **inside the plugin**.
  * Data sanitation & PII redaction tests.
* **Security scans**: dep vulns, secret scan, static analysis clean.
* **SBOM + license review** completed.
* **Reproducible build & signatures**:

  * Build script, hash, and signature attached; supply provenance attestation.

# Platform acceptance criteria (platform responsibilities)

* **Verify** signature, SBOM hash, and manifest at load.
* **Stamp** all outputs and logs with `plugin_id`, `artifact_digest`, `run_id`.
* **Observe** network metadata; compare observed hosts to declared allowlist; generate a **signed conformance report** per run.
* **Revocation hooks** in control plane; instant kill switch; clear operator runbooks.

# Why not hard intercept?

* Intercepting every network call in-process is **bypassable** in Python and encourages the mindset “the platform will stop me anyway.”
  If you add strong OS-level blocks, you’re back to the platform being the policy owner. That’s fine if your risk appetite demands it, but it **shifts accountability** from the plugin to the platform.

* With the model above you can choose policy:

  * **High-trust**: observe only, act on breaches via revocation.
  * **Medium-trust**: observe + auto-quarantine on breach conditions.
  * **Low-trust**: container egress allowlist enforced by ops — but acknowledge that now **ops owns part of the permission story**.

# Practical next steps (tight and simple)

* Require a **`PLUGIN_MANIFEST.json`** embedded in each plugin, signed alongside the wheel:

  ```json
  {
    "plugin_id": "azure_openai_embeddings",
    "artifact_digest": "sha256:…",
    "allowed_egress": ["*.openai.azure.com"],
    "data_classes": ["official", "secret"],
    "sdk_allowlist": ["openai>=2.0,<3.0"],
    "built_by": "ci/elspeth",
    "built_at": "2025-10-15T10:32:01Z"
  }
  ```

* On load: verify signature + digest; if missing → **hard fail**.
* At runtime: emit **conformance events** (`destination_host`, `scheme`, `port`, `plugin_id`, `digest`, `mode`).
* Nightly job: **diff manifest vs observed**, send report to plugin owner; if non-conforming and policy requires, add digest to **CRL**.

# Estimative probabilities (WEP)

* The model **preserves accountability** with strong provenance and revocation while keeping the platform neutral on day-to-day policy: **Almost certain** (95–99%).
* Observation-only telemetry + conformance auditing will surface unauthorised egress reliably in practice: **Highly likely** (80–95%).
* Full prevention without shifting accountability requires OS/network policy that, by definition, **moves ownership to ops**: **Almost certain** (95–99%).
