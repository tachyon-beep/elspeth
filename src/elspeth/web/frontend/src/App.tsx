import { useEffect, useState } from "react";
import "./App.css";
import * as api from "./api/client";
import { AuthGuard } from "./components/common/AuthGuard";
import { Layout } from "./components/common/Layout";
import { SessionSidebar } from "./components/sessions/SessionSidebar";
import { ChatPanel } from "./components/chat/ChatPanel";
import { InspectorPanel } from "./components/inspector/InspectorPanel";
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
        {systemStatus && !systemStatus.composer_available && (
          <div
            role="alert"
            style={{
              padding: "10px 14px",
              backgroundColor: "rgba(255, 102, 102, 0.12)",
              color: "var(--color-error)",
              borderBottom: "1px solid rgba(255, 102, 102, 0.3)",
              fontSize: 13,
            }}
          >
            Service unavailable: {systemStatus.composer_reason ?? "The composer cannot reach a usable LLM right now."}
          </div>
        )}
        <div style={{ flex: 1, minHeight: 0 }}>
          <Layout
            sidebar={<SessionSidebar />}
            chat={<ChatPanel />}
            inspector={<InspectorPanel />}
          />
        </div>
      </div>
    </AuthGuard>
  );
}

export default App;
