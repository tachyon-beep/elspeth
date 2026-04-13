// ============================================================================
// YamlView
//
// Read-only display of the generated ELSPETH pipeline YAML with Monaco Editor.
// The YAML is fetched from GET /api/sessions/{id}/state/yaml on version change
// (not generated client-side).
//
// Features:
// - Monaco Editor with YAML syntax highlighting
// - Copy-to-clipboard button
// - Download button for YAML export
// - Theme-aware (light/dark)
//
// Empty state when no composition state exists.
// ============================================================================

import { useState, useEffect, useCallback, useRef } from "react";
import Editor from "@monaco-editor/react";
import { useSessionStore } from "@/stores/sessionStore";
import { useTheme } from "@/hooks/useTheme";
import * as api from "@/api/client";

// Timeout for Monaco to initialize before falling back to plain text
const MONACO_TIMEOUT_MS = 5000;

export function YamlView() {
  const compositionState = useSessionStore((s) => s.compositionState);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const [yaml, setYaml] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [monacoReady, setMonacoReady] = useState(false);
  const [monacoFailed, setMonacoFailed] = useState(false);
  const monacoTimeoutRef = useRef<number | null>(null);
  const { resolvedTheme } = useTheme();

  // Set up Monaco timeout - fallback to plain text if it doesn't load
  useEffect(() => {
    if (yaml && !monacoReady && !monacoFailed) {
      monacoTimeoutRef.current = window.setTimeout(() => {
        console.warn("[YamlView] Monaco editor timed out, falling back to plain text");
        setMonacoFailed(true);
      }, MONACO_TIMEOUT_MS);
    }
    return () => {
      if (monacoTimeoutRef.current) {
        window.clearTimeout(monacoTimeoutRef.current);
      }
    };
  }, [yaml, monacoReady, monacoFailed]);

  const handleMonacoMount = useCallback(() => {
    setMonacoReady(true);
    if (monacoTimeoutRef.current) {
      window.clearTimeout(monacoTimeoutRef.current);
    }
  }, []);

  // Fetch YAML from the backend whenever composition state version changes
  const version = compositionState?.version ?? null;

  useEffect(() => {
    if (!activeSessionId || version === null) {
      setYaml(null);
      setIsLoading(false);  // Reset loading state on early return
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
    <div style={{ position: "relative", height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Toolbar: Copy + Download buttons */}
      <div
        style={{
          display: "flex",
          gap: 6,
          padding: "8px 12px",
          borderBottom: "1px solid var(--color-border)",
          backgroundColor: "var(--color-surface)",
          flexShrink: 0,
        }}
      >
        <button
          onClick={handleCopy}
          aria-label={copied ? "Copied to clipboard" : "Copy YAML to clipboard"}
          className="btn"
          style={{
            padding: "4px 10px",
            fontSize: 12,
            backgroundColor: copied
              ? "var(--color-success-bg)"
              : "var(--color-surface-elevated)",
            color: copied
              ? "var(--color-success)"
              : "var(--color-text-secondary)",
          }}
        >
          {copied ? "Copied!" : "Copy"}
        </button>
        <button
          onClick={handleDownload}
          aria-label="Download YAML file"
          className="btn"
          style={{
            padding: "4px 10px",
            fontSize: 12,
          }}
        >
          Download
        </button>
      </div>

      {/* Monaco Editor with plain text fallback */}
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {monacoFailed ? (
          // Plain text fallback when Monaco fails to load
          <pre
            style={{
              margin: 0,
              padding: 16,
              fontSize: 12,
              fontFamily: "var(--font-mono)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: "var(--color-text)",
              backgroundColor: "var(--color-surface)",
            }}
          >
            {yaml}
          </pre>
        ) : (
          <Editor
            height="100%"
            language="yaml"
            theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
            value={yaml}
            onMount={handleMonacoMount}
            loading={
              <div style={{ padding: 24, color: "var(--color-text-muted)", fontSize: 13 }}>
                Initializing editor...
              </div>
            }
            options={{
              readOnly: true,
              minimap: { enabled: false },
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              fontSize: 12,
              fontFamily: "var(--font-mono)",
              padding: { top: 8, bottom: 8 },
              scrollbar: {
                verticalScrollbarSize: 8,
                horizontalScrollbarSize: 8,
              },
            }}
          />
        )}
      </div>
    </div>
  );
}
