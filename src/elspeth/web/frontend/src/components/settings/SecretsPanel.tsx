// src/components/settings/SecretsPanel.tsx
import { useState, useEffect, useCallback, useRef } from "react";
import { useSecretsStore } from "@/stores/secretsStore";
import type { SecretInventoryItem } from "@/types/api";

interface SecretsPanelProps {
  onClose: () => void;
}

function ScopeBadge({ scope }: { scope: SecretInventoryItem["scope"] }) {
  const colors: Record<SecretInventoryItem["scope"], { bg: string; text: string }> = {
    user: { bg: "var(--color-accent-muted, #d1fae5)", text: "var(--color-accent, #065f46)" },
    server: { bg: "var(--color-info-bg, #dbeafe)", text: "var(--color-info, #1e40af)" },
    org: { bg: "var(--color-surface-raised, #f3f4f6)", text: "var(--color-text-secondary)" },
  };
  const { bg, text } = colors[scope] ?? colors.org;
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        padding: "1px 6px",
        borderRadius: 3,
        backgroundColor: bg,
        color: text,
        marginLeft: 6,
      }}
    >
      {scope}
    </span>
  );
}

function AvailabilityDot({ available }: { available: boolean }) {
  return (
    <span
      aria-label={available ? "Available" : "Unavailable"}
      title={available ? "Available" : "Not set"}
      style={{
        display: "inline-block",
        width: 12,
        height: 12,
        borderRadius: "50%",
        backgroundColor: available
          ? "var(--color-success, #16a34a)"
          : "var(--color-text-muted, #9ca3af)",
        flexShrink: 0,
      }}
    />
  );
}

/**
 * Secrets settings panel — modal overlay.
 *
 * Write-only entry form for user-scoped secrets plus an inventory display
 * showing all available secret references (metadata only, never values).
 *
 * SECURITY:
 * - Value input uses type="password" — no browser autocomplete for the secret value.
 * - Value field is cleared immediately after successful submission.
 * - The store never retains the value after the API call completes.
 * - No "show password" toggle is provided.
 */
export function SecretsPanel({ onClose }: SecretsPanelProps) {
  const { secrets, isLoading, error, loadSecrets, createSecret, deleteSecret } =
    useSecretsStore();
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSecrets();
  }, [loadSecrets]);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Focus trap: constrain Tab within the modal
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    // Focus the first input on mount
    const firstInput = modal.querySelector<HTMLElement>("input, button");
    firstInput?.focus();

    function handleTab(e: KeyboardEvent) {
      if (e.key !== "Tab" || !modal) return;
      const focusable = modal.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleTab);
    return () => document.removeEventListener("keydown", handleTab);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!name.trim() || !value) return;
      setIsSubmitting(true);
      await createSecret(name.trim(), value);
      // SECURITY: clear value immediately after submission — it must never
      // linger in component state or the store after the API call.
      setValue("");
      setName("");
      setIsSubmitting(false);
    },
    [name, value, createSecret],
  );

  const handleDelete = useCallback(
    (secretName: string) => {
      deleteSecret(secretName);
    },
    [deleteSecret],
  );

  return (
    <>
      {/* Backdrop */}
      <div
        role="presentation"
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(0,0,0,0.45)",
          zIndex: 100,
        }}
      />

      {/* Modal */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Secrets settings"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: 101,
          width: 480,
          maxWidth: "calc(100vw - 32px)",
          maxHeight: "calc(100vh - 64px)",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "var(--color-surface, #fff)",
          borderRadius: 8,
          boxShadow: "0 8px 32px rgba(0,0,0,0.25)",
          border: "1px solid var(--color-border)",
          fontSize: 13,
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 16px",
            borderBottom: "1px solid var(--color-border)",
            flexShrink: 0,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
            API Keys &amp; Secrets
          </h2>
          <button
            onClick={onClose}
            aria-label="Close secrets panel"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--color-text-muted)",
              fontSize: 18,
              lineHeight: 1,
              padding: "2px 6px",
              borderRadius: 4,
              minWidth: 44,
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ×
          </button>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
          {/* Entry form */}
          <section aria-labelledby="secrets-add-heading">
            <h3
              id="secrets-add-heading"
              style={{
                margin: "0 0 10px",
                fontSize: 12,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--color-text-secondary)",
              }}
            >
              Add or update a secret
            </h3>
            <form onSubmit={handleSubmit} noValidate>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div>
                  <label
                    htmlFor="secret-name"
                    style={{
                      display: "block",
                      marginBottom: 4,
                      fontSize: 12,
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    Name
                  </label>
                  <input
                    id="secret-name"
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="e.g. OPENAI_API_KEY"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 10px",
                      borderRadius: 4,
                      border: "1px solid var(--color-border)",
                      backgroundColor: "var(--color-surface-input, var(--color-surface))",
                      color: "var(--color-text)",
                      fontSize: 13,
                      boxSizing: "border-box",
                    }}
                  />
                </div>
                <div>
                  <label
                    htmlFor="secret-value"
                    style={{
                      display: "block",
                      marginBottom: 4,
                      fontSize: 12,
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    Value
                  </label>
                  {/* SECURITY: type="password" — value never displayed in plaintext.
                      No "show" toggle is intentional. */}
                  <input
                    id="secret-value"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Paste your secret value here"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 10px",
                      borderRadius: 4,
                      border: "1px solid var(--color-border)",
                      backgroundColor: "var(--color-surface-input, var(--color-surface))",
                      color: "var(--color-text)",
                      fontSize: 13,
                      boxSizing: "border-box",
                    }}
                  />
                </div>
                <button
                  type="submit"
                  disabled={!name.trim() || !value || isSubmitting}
                  className="btn btn-primary"
                  style={{
                    alignSelf: "flex-start",
                    padding: "6px 16px",
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: !name.trim() || !value || isSubmitting ? "not-allowed" : "pointer",
                    opacity: !name.trim() || !value || isSubmitting ? 0.55 : 1,
                  }}
                >
                  {isSubmitting ? "Saving…" : "Save secret"}
                </button>
              </div>
            </form>
          </section>

          {/* Error banner */}
          {error && (
            <div
              role="alert"
              style={{
                marginTop: 12,
                padding: "6px 10px",
                borderRadius: 4,
                backgroundColor: "var(--color-error-bg)",
                color: "var(--color-error)",
                fontSize: 12,
              }}
            >
              {error}
            </div>
          )}

          {/* Inventory */}
          <section aria-labelledby="secrets-inventory-heading" style={{ marginTop: 20 }}>
            <h3
              id="secrets-inventory-heading"
              style={{
                margin: "0 0 10px",
                fontSize: 12,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--color-text-secondary)",
              }}
            >
              Secret inventory
            </h3>

            {isLoading ? (
              <div
                style={{
                  padding: "12px 0",
                  color: "var(--color-text-muted)",
                  textAlign: "center",
                }}
              >
                Loading…
              </div>
            ) : secrets.length === 0 ? (
              <div
                style={{
                  padding: "12px 0",
                  color: "var(--color-text-muted)",
                  textAlign: "center",
                }}
              >
                No secrets configured. Add one above.
              </div>
            ) : (
              <ul
                role="list"
                style={{
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                }}
              >
                {secrets.map((secret) => (
                  <li
                    key={secret.name}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "7px 10px",
                      borderRadius: 4,
                      border: "1px solid var(--color-border)",
                      backgroundColor: "var(--color-surface-raised, var(--color-surface))",
                    }}
                  >
                    <AvailabilityDot available={secret.available} />

                    <span
                      style={{
                        flex: 1,
                        fontFamily: "monospace",
                        fontSize: 12,
                        wordBreak: "break-all",
                        color: "var(--color-text)",
                      }}
                    >
                      {secret.name}
                    </span>

                    <ScopeBadge scope={secret.scope} />

                    {/* Server-scoped and org-scoped secrets are read-only — no delete */}
                    {secret.scope === "user" && (
                      <button
                        onClick={() => handleDelete(secret.name)}
                        aria-label={`Delete secret ${secret.name}`}
                        title="Delete"
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--color-error, #dc2626)",
                          fontSize: 14,
                          padding: "2px 4px",
                          lineHeight: 1,
                          borderRadius: 3,
                          flexShrink: 0,
                          minWidth: 44,
                          minHeight: 44,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        ×
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p
            style={{
              marginTop: 16,
              fontSize: 11,
              color: "var(--color-text-muted)",
              lineHeight: 1.5,
            }}
          >
            Secrets are encrypted at rest. Values are never shown after saving.
            Server-scoped secrets are configured by an administrator and cannot
            be deleted here.
          </p>
        </div>
      </div>
    </>
  );
}
