// ============================================================================
// YamlView
//
// Read-only syntax-highlighted YAML display using prism-react-renderer.
// The YAML is fetched from GET /api/sessions/{id}/state/yaml on version change.
//
// Features:
// - Syntax highlighting with line numbers
// - Copy-to-clipboard button
// - Download button for YAML export
// - Theme-aware (light/dark)
//
// Empty state when no composition state exists.
// ============================================================================

import { useState, useEffect, useCallback } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { useSessionStore } from "@/stores/sessionStore";
import { useTheme } from "@/hooks/useTheme";
import * as api from "@/api/client";

export function YamlView() {
  const compositionState = useSessionStore((s) => s.compositionState);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const [yaml, setYaml] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const { resolvedTheme } = useTheme();

  // Fetch YAML from the backend whenever composition state version changes
  const version = compositionState?.version ?? null;

  useEffect(() => {
    if (!activeSessionId || version === null) {
      setYaml(null);
      setIsLoading(false);
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
    }
  }, [yaml]);

  const handleDownload = useCallback(() => {
    if (!yaml) return;
    const blob = new Blob([yaml], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pipeline-v${compositionState?.version ?? 1}.yaml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [yaml, compositionState?.version]);

  // Empty state
  if (!compositionState || version === null) {
    return (
      <div className="empty-state">
        YAML will appear here once your pipeline has components.
      </div>
    );
  }

  // Loading state
  if (isLoading && !yaml) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="yaml-loading"
      >
        Loading YAML...
      </div>
    );
  }

  // No YAML returned (unexpected empty response)
  if (!yaml) {
    return (
      <div className="empty-state">
        YAML will appear here once your pipeline has components.
      </div>
    );
  }

  const highlightTheme = resolvedTheme === "dark" ? themes.vsDark : themes.vsLight;

  return (
    <div className="yaml-view">
      {/* Toolbar: Copy + Download buttons */}
      <div className="yaml-view-toolbar">
        <button
          onClick={handleCopy}
          aria-label={copied ? "Copied to clipboard" : "Copy YAML to clipboard"}
          className="btn yaml-toolbar-btn"
          style={{
            backgroundColor: copied
              ? "var(--color-success-bg)"
              : undefined,
            color: copied
              ? "var(--color-success)"
              : undefined,
          }}
        >
          {copied ? "Copied!" : "Copy"}
        </button>
        <button
          onClick={handleDownload}
          aria-label="Download YAML file"
          className="btn yaml-toolbar-btn"
        >
          Download
        </button>
      </div>

      {/* Syntax-highlighted YAML */}
      <div className="yaml-view-content">
        <Highlight theme={highlightTheme} code={yaml} language="yaml">
          {({ tokens, getLineProps, getTokenProps }) => (
            <pre className="yaml-view-pre">
              {tokens.map((line, i) => (
                <div key={i} {...getLineProps({ line })} className="yaml-view-line">
                  <span className="yaml-view-line-number">{i + 1}</span>
                  <span className="yaml-view-line-content">
                    {line.map((token, key) => (
                      <span key={key} {...getTokenProps({ token })} />
                    ))}
                  </span>
                </div>
              ))}
            </pre>
          )}
        </Highlight>
      </div>
    </div>
  );
}
