import { useEffect, useState, useCallback, useRef } from "react";
import "./App.css";
import * as api from "./api/client";
import { AuthGuard } from "./components/common/AuthGuard";
import { Layout } from "./components/common/Layout";
import { CommandPalette } from "./components/common/CommandPalette";
import { SessionSidebar } from "./components/sessions/SessionSidebar";
import { ChatPanel } from "./components/chat/ChatPanel";
import { InspectorPanel } from "./components/inspector/InspectorPanel";
import { SecretsPanel } from "./components/settings/SecretsPanel";
import { initStoreSubscriptions } from "./stores/subscriptions";
import { useSessionStore } from "./stores/sessionStore";
import type { SystemStatus } from "./types/index";

// Health check interval in milliseconds (30 seconds)
const HEALTH_CHECK_INTERVAL = 30_000;

// Wire up cross-store subscriptions once at module load time.
// This must run before any component renders so that version-change
// auto-clear is active from the first render.
initStoreSubscriptions();

/**
 * Top-level application component.
 *
 * Single composition root: AuthGuard gates the entire app behind authentication,
 * then Layout renders the three-panel grid with SessionSidebar, ChatPanel, and
 * InspectorPanel. No router in v1 -- the entire application is a single page.
 */
function App() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
  const [showSecrets, setShowSecrets] = useState(false);
  const [showPalette, setShowPalette] = useState(false);
  const healthCheckRef = useRef<number | null>(null);

  const createSession = useSessionStore((s) => s.createSession);

  const openSecrets = useCallback(() => setShowSecrets(true), []);
  const closeSecrets = useCallback(() => setShowSecrets(false), []);
  const closePalette = useCallback(() => setShowPalette(false), []);

  // Check backend health
  const checkHealth = useCallback(async () => {
    try {
      const status = await api.fetchSystemStatus();
      setSystemStatus(status);
      setBackendAvailable(true);
    } catch {
      setSystemStatus(null);
      setBackendAvailable(false);
    }
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ctrl+K / Cmd+K: Open command palette
      if (e.key === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setShowPalette(true);
        return;
      }

      // Ctrl+N / Cmd+N: New session
      if (e.key === "n" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        createSession();
        return;
      }

      // Ctrl+/ / Cmd+/: Focus chat input
      if (e.key === "/" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const input = document.querySelector<HTMLTextAreaElement>(
          "[data-chat-input]",
        );
        input?.focus();
        return;
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [createSession]);

  // Initial health check and periodic polling
  useEffect(() => {
    checkHealth();

    // Set up periodic health checks
    healthCheckRef.current = window.setInterval(checkHealth, HEALTH_CHECK_INTERVAL);

    return () => {
      if (healthCheckRef.current !== null) {
        window.clearInterval(healthCheckRef.current);
      }
    };
  }, [checkHealth]);

  return (
    <AuthGuard>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
        }}
      >
        <h1 className="sr-only">ELSPETH Pipeline Composer</h1>

        {/* Backend unavailable banner */}
        {backendAvailable === false && (
          <div
            role="alert"
            style={{
              padding: "10px 14px",
              backgroundColor: "var(--color-error-bg)",
              color: "var(--color-error)",
              borderBottom: "1px solid var(--color-error-border)",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span>
              <strong>Backend unavailable</strong> — Cannot connect to the
              ELSPETH server. Check that the backend is running.
            </span>
            <button
              onClick={checkHealth}
              aria-label="Retry connection"
              title="Retry connection"
              style={{
                background: "none",
                border: "1px solid var(--color-error-border)",
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--color-error)",
                fontSize: 12,
                padding: "2px 8px",
                marginLeft: 12,
                flexShrink: 0,
              }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Composer unavailable banner (backend is up but LLM not configured) */}
        {backendAvailable && systemStatus && !systemStatus.composer_available && (
          <div
            role="alert"
            style={{
              padding: "10px 14px",
              backgroundColor: "var(--color-error-bg)",
              color: "var(--color-error)",
              borderBottom: "1px solid var(--color-error-border)",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span>
              Service unavailable:{" "}
              {systemStatus.composer_reason ??
                "The composer cannot reach a usable LLM right now."}
            </span>
            <button
              onClick={openSecrets}
              aria-label="Open secrets settings"
              title="Configure API keys"
              style={{
                background: "none",
                border: "1px solid var(--color-error-border)",
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--color-error)",
                fontSize: 12,
                padding: "2px 8px",
                marginLeft: 12,
                flexShrink: 0,
              }}
            >
              ⚙ API Keys
            </button>
          </div>
        )}
        <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
          <Layout
            sidebar={<SessionSidebar />}
            chat={<ChatPanel onOpenSecrets={openSecrets} />}
            inspector={<InspectorPanel />}
          />
        </div>

        {showSecrets && <SecretsPanel onClose={closeSecrets} />}
        <CommandPalette isOpen={showPalette} onClose={closePalette} />
      </div>
    </AuthGuard>
  );
}

export default App;
