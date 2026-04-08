import { useEffect, useState, useCallback } from "react";
import "./App.css";
import * as api from "./api/client";
import { AuthGuard } from "./components/common/AuthGuard";
import { Layout } from "./components/common/Layout";
import { SessionSidebar } from "./components/sessions/SessionSidebar";
import { ChatPanel } from "./components/chat/ChatPanel";
import { InspectorPanel } from "./components/inspector/InspectorPanel";
import { SecretsPanel } from "./components/settings/SecretsPanel";
import { initStoreSubscriptions } from "./stores/subscriptions";
import type { SystemStatus } from "./types/index";

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
  const [showSecrets, setShowSecrets] = useState(false);

  const openSecrets = useCallback(() => setShowSecrets(true), []);
  const closeSecrets = useCallback(() => setShowSecrets(false), []);

  // Global keyboard shortcut: Ctrl+/ (or Cmd+/ on Mac) focuses the chat input
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "/" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const input = document.querySelector<HTMLTextAreaElement>(
          "[data-chat-input]",
        );
        input?.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    api
      .fetchSystemStatus()
      .then(setSystemStatus)
      .catch(() => {
        setSystemStatus(null);
      });
  }, []);

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
        {systemStatus && !systemStatus.composer_available && (
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
      </div>
    </AuthGuard>
  );
}

export default App;
