// ============================================================================
// YamlView
//
// Read-only display of the generated ELSPETH pipeline YAML. The YAML is
// fetched from GET /api/sessions/{id}/state/yaml on version change (not
// generated client-side). Uses prism-react-renderer for syntax highlighting.
// Copy-to-clipboard button with brief "Copied!" confirmation.
//
// Empty state when no composition state exists.
// ============================================================================

import { useState, useEffect, useCallback } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { useSessionStore } from "@/stores/sessionStore";
import * as api from "@/api/client";

export function YamlView() {
  const compositionState = useSessionStore((s) => s.compositionState);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const [yaml, setYaml] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Fetch YAML from the backend whenever composition state version changes
  const version = compositionState?.version ?? null;

  useEffect(() => {
    if (!activeSessionId || version === null) {
      setYaml(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);

    api
      .fetchYaml(activeSessionId)
      .then(({ yaml: text }) => {
        if (!cancelled) {
          setYaml(text);
          setIsLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setYaml(null);
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeSessionId, version]);

  const handleCopy = useCallback(async () => {
    if (!yaml) return;
    try {
      await navigator.clipboard.writeText(yaml);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may fail in some contexts (e.g. insecure origin)
      // No fallback needed for MVP
    }
  }, [yaml]);

  // Empty state
  if (!compositionState || version === null) {
    return (
      <div
        className="empty-state"
        style={{
          padding: 24,
          fontSize: 14,
        }}
      >
        YAML will appear here once your pipeline has components.
      </div>
    );
  }

  // Loading state
  if (isLoading && !yaml) {
    return (
      <div
        style={{
          padding: 24,
          color: "var(--color-text-muted)",
          fontSize: 13,
          textAlign: "center",
        }}
      >
        Loading YAML...
      </div>
    );
  }

  // No YAML returned (unexpected empty response)
  if (!yaml) {
    return (
      <div
        className="empty-state"
        style={{
          padding: 24,
          fontSize: 14,
        }}
      >
        YAML will appear here once your pipeline has components.
      </div>
    );
  }

  return (
    <div style={{ position: "relative", height: "100%" }}>
      {/* Copy-to-clipboard button */}
      <button
        onClick={handleCopy}
        aria-label={copied ? "Copied to clipboard" : "Copy YAML to clipboard"}
        className="btn"
        style={{
          position: "absolute",
          top: 8,
          right: 8,
          padding: "4px 10px",
          fontSize: 12,
          backgroundColor: copied
            ? "var(--color-success-bg)"
            : "var(--color-surface-elevated)",
          color: copied
            ? "var(--color-success)"
            : "var(--color-text-secondary)",
          zIndex: 1,
        }}
      >
        {copied ? "Copied!" : "Copy"}
      </button>

      {/* Syntax-highlighted YAML */}
      <Highlight theme={themes.dracula} code={yaml} language="yaml">
        {({ style, tokens, getLineProps, getTokenProps }) => (
          <pre
            style={{
              ...style,
              margin: 0,
              padding: "12px 16px",
              paddingTop: 36, // Space for the copy button
              overflow: "auto",
              height: "100%",
              fontSize: 12,
              lineHeight: 1.5,
              boxSizing: "border-box",
              backgroundColor: "var(--color-surface)",
            }}
          >
            {tokens.map((line, i) => {
              const lineProps = getLineProps({ line });
              return (
                <div key={i} {...lineProps}>
                  {line.map((token, j) => {
                    const tokenProps = getTokenProps({ token });
                    return <span key={j} {...tokenProps} />;
                  })}
                </div>
              );
            })}
          </pre>
        )}
      </Highlight>
    </div>
  );
}
