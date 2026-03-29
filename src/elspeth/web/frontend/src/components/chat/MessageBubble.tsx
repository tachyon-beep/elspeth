// src/components/chat/MessageBubble.tsx
import { useState } from "react";
import type { ChatMessage } from "@/types/api";

interface MessageBubbleProps {
  message: ChatMessage;
  onRetry?: (messageId: string) => void;
}

export function MessageBubble({ message, onRetry }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const [toolsExpanded, setToolsExpanded] = useState(false);

  // System messages: centre-aligned full-width banner, muted colour,
  // italic text, no sender label. Used for audit markers like
  // "Pipeline reverted to version N."
  if (isSystem) {
    return (
      <div
        className="message-bubble message-bubble--system"
        style={{
          display: "flex",
          justifyContent: "center",
          padding: "4px 16px",
        }}
      >
        <div
          className="bubble bubble-system"
          role="status"
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`message-bubble message-bubble--${message.role}`}
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        padding: "4px 16px",
      }}
    >
      <div
        className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}
        style={{
          maxWidth: "80%",
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {message.content}

        {isUser && message.local_status === "failed" && onRetry && (
          <div
            style={{
              marginTop: 8,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span
              style={{
                fontSize: 12,
                color: "var(--color-error)",
              }}
            >
              No LLM available. Message not processed.
            </span>
            <button
              onClick={() => onRetry(message.id)}
              style={{
                border: "1px solid var(--color-border-strong)",
                backgroundColor: "transparent",
                color: "var(--color-text)",
                borderRadius: 4,
                cursor: "pointer",
                fontSize: 12,
                padding: "4px 8px",
              }}
            >
              Retry
            </button>
          </div>
        )}

        {isUser && message.local_status === "pending" && (
          <div
            style={{
              marginTop: 8,
              fontSize: 12,
              color: "var(--color-text-muted)",
            }}
          >
            Sending...
          </div>
        )}

        {/* Tool calls section (assistant messages only) */}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div
            style={{
              marginTop: 8,
              borderTop: "1px solid var(--color-border-strong)",
              paddingTop: 6,
            }}
          >
            <button
              onClick={() => setToolsExpanded(!toolsExpanded)}
              aria-expanded={toolsExpanded}
              aria-label={`Tool calls (${message.tool_calls.length})`}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                fontSize: 12,
                color: "var(--color-text-muted)",
                padding: 0,
              }}
            >
              {toolsExpanded ? "\u25BC" : "\u25B6"} Tool calls (
              {message.tool_calls.length})
            </button>
            {toolsExpanded && (
              <ul
                style={{
                  margin: "4px 0 0",
                  paddingLeft: 16,
                  fontSize: 12,
                }}
              >
                {message.tool_calls.map((tc, i) => (
                  <li
                    key={tc.id ?? i}
                    style={{
                      color: "var(--color-text-secondary)",
                      marginBottom: 4,
                    }}
                  >
                    <strong>{tc.function.name}</strong>
                    {tc.function.arguments && (
                      <details style={{ marginTop: 2 }}>
                        <summary
                          style={{
                            cursor: "pointer",
                            color: "var(--color-text-muted)",
                            fontSize: 11,
                          }}
                        >
                          Arguments
                        </summary>
                        <pre
                          style={{
                            margin: "2px 0 0",
                            padding: 4,
                            backgroundColor: "var(--color-surface-elevated)",
                            borderRadius: 3,
                            fontSize: 11,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}
                        >
                          {tc.function.arguments}
                        </pre>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
