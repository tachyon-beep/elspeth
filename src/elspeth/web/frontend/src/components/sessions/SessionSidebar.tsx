// src/components/sessions/SessionSidebar.tsx
//
// Session list sidebar. Always renders at full width -- collapse/expand
// is controlled by Layout.tsx via CSS grid column sizing.
import { useState, useCallback } from "react";
import { useSession } from "@/hooks/useSession";
import { useAuth } from "@/hooks/useAuth";

/** Format a date string as a relative time ("2 min ago", "yesterday"). */
function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay === 1) return "yesterday";
  return `${diffDay}d ago`;
}

export function SessionSidebar() {
  const { sessions, activeSessionId, createSession, selectSession, archiveSession } =
    useSession();
  const { user, logout } = useAuth();
  const [isCreating, setIsCreating] = useState(false);

  const handleCreateSession = useCallback(async () => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      await createSession();
    } finally {
      setIsCreating(false);
    }
  }, [isCreating, createSession]);

  return (
    <aside
      className="session-sidebar"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
      aria-label="Sessions sidebar"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 12px 8px",
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <span
          style={{
            fontWeight: 600,
            fontSize: 14,
            color: "var(--color-text)",
          }}
        >
          Sessions
        </span>
      </div>

      {/* Session list */}
      <nav
        style={{ flex: 1, overflowY: "auto" }}
        aria-label="Session list"
      >
        {sessions.length === 0 ? (
          <div
            style={{
              padding: 16,
              color: "var(--color-text-muted)",
              fontSize: 13,
              textAlign: "center",
            }}
          >
            No sessions yet. Click the button below to start.
          </div>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {sessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <li
                  key={session.id}
                  style={{
                    display: "flex",
                    alignItems: "stretch",
                  }}
                >
                  <button
                    onClick={() => selectSession(session.id)}
                    aria-current={isActive ? "true" : undefined}
                    aria-label={`Session: ${session.title}, ${relativeTime(session.updated_at)}`}
                    style={{
                      display: "block",
                      flex: 1,
                      minWidth: 0,
                      padding: "10px 12px",
                      border: "none",
                      borderLeft: isActive
                        ? "3px solid var(--color-accent)"
                        : "3px solid transparent",
                      backgroundColor: isActive
                        ? "var(--color-surface-hover)"
                        : "transparent",
                      cursor: "pointer",
                      textAlign: "left",
                      fontSize: 13,
                      color: "var(--color-text)",
                    }}
                  >
                    <div
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        fontWeight: isActive ? 600 : 400,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      {session.forked_from_session_id && (
                        <span
                          title="Forked session"
                          aria-label="Forked session"
                          style={{
                            fontSize: 10,
                            color: "var(--color-text-muted)",
                            flexShrink: 0,
                          }}
                        >
                          &#x2442;
                        </span>
                      )}
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                        {session.title}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--color-text-muted)",
                        marginTop: 2,
                      }}
                    >
                      {relativeTime(session.updated_at)}
                    </div>
                  </button>
                  <button
                    onClick={() => {
                      if (window.confirm(`Archive session "${session.title}"?`)) {
                        archiveSession(session.id);
                      }
                    }}
                    aria-label={`Archive session: ${session.title}`}
                    title="Archive session"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 32,
                      border: "none",
                      backgroundColor: "transparent",
                      color: "var(--color-text-muted)",
                      cursor: "pointer",
                      fontSize: 14,
                      opacity: 0.5,
                      flexShrink: 0,
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.opacity = "1";
                      e.currentTarget.style.color = "var(--color-error)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.opacity = "0.5";
                      e.currentTarget.style.color = "var(--color-text-muted)";
                    }}
                  >
                    {"\u00D7"}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* New session button */}
      <div style={{ padding: 8, borderTop: "1px solid var(--color-border)" }}>
        <button
          onClick={handleCreateSession}
          disabled={isCreating}
          aria-label={isCreating ? "Creating session" : "Create new session"}
          style={{
            display: "block",
            width: "100%",
            padding: "8px 12px",
            backgroundColor: isCreating
              ? "var(--color-surface-elevated)"
              : "var(--color-accent)",
            color: isCreating
              ? "var(--color-text-muted)"
              : "var(--color-text-inverse)",
            border: "none",
            borderRadius: 4,
            cursor: isCreating ? "not-allowed" : "pointer",
            fontSize: 13,
          }}
        >
          {isCreating ? "Creating..." : "+ New Session"}
        </button>
      </div>

      {/* User identity + logout */}
      {user && (
        <div
          style={{
            padding: "8px 12px",
            borderTop: "1px solid var(--color-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <span
            style={{
              fontSize: 12,
              color: "var(--color-text-secondary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={user.username}
          >
            {user.display_name || user.username}
          </span>
          <button
            onClick={logout}
            aria-label="Sign out"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              color: "var(--color-text-muted)",
              padding: "4px 8px",
              borderRadius: 4,
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </aside>
  );
}
