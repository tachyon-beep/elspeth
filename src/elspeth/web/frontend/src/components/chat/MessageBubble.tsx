// src/components/chat/MessageBubble.tsx
import { useState, useCallback, useRef, useEffect } from "react";
import type { ChatMessage } from "@/types/api";

interface MessageBubbleProps {
  message: ChatMessage;
  isComposing?: boolean;
  onRetry?: (messageId: string) => void;
  onFork?: (messageId: string, newContent: string) => void;
}

export function MessageBubble({ message, isComposing, onRetry, onFork }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const editRef = useRef<HTMLTextAreaElement>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may fail in insecure contexts
    }
  }, [message.content]);

  const handleEditStart = useCallback(() => {
    setEditContent(message.content);
    setIsEditing(true);
  }, [message.content]);

  const handleEditCancel = useCallback(() => {
    setIsEditing(false);
    setEditContent(message.content);
  }, [message.content]);

  const handleForkSubmit = useCallback(() => {
    if (onFork && editContent.trim()) {
      onFork(message.id, editContent.trim());
      setIsEditing(false);
    }
  }, [onFork, message.id, editContent]);

  useEffect(() => {
    if (isEditing && editRef.current) {
      editRef.current.focus();
      editRef.current.setSelectionRange(
        editRef.current.value.length,
        editRef.current.value.length,
      );
    }
  }, [isEditing]);

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
          position: "relative",
        }}
      >
        {/* Copy button — visible on hover via CSS, always accessible on touch */}
        {!isSystem && (
          <button
            onClick={handleCopy}
            aria-label={copied ? "Copied to clipboard" : "Copy message"}
            className="bubble-copy-btn"
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              color: "var(--color-text-muted)",
              padding: "2px 6px",
              borderRadius: 4,
              minWidth: 44,
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: copied ? 1 : undefined,
            }}
          >
            {copied ? "Copied!" : "\u2398"}
          </button>
        )}

        {isUser && isEditing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <textarea
              ref={editRef}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  handleForkSubmit();
                } else if (e.key === "Escape") {
                  handleEditCancel();
                }
              }}
              aria-label="Edit message"
              style={{
                width: "100%",
                minHeight: 60,
                padding: 8,
                border: "1px solid var(--color-border-strong)",
                borderRadius: 4,
                fontSize: 14,
                lineHeight: 1.5,
                fontFamily: "inherit",
                resize: "vertical",
                backgroundColor: "var(--color-surface)",
                color: "var(--color-text)",
              }}
            />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={handleEditCancel}
                style={{
                  border: "1px solid var(--color-border-strong)",
                  backgroundColor: "transparent",
                  color: "var(--color-text)",
                  borderRadius: 4,
                  cursor: "pointer",
                  fontSize: 12,
                  padding: "4px 12px",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleForkSubmit}
                disabled={!editContent.trim()}
                style={{
                  border: "none",
                  backgroundColor: "var(--color-primary)",
                  color: "var(--color-on-primary, #fff)",
                  borderRadius: 4,
                  cursor: editContent.trim() ? "pointer" : "not-allowed",
                  fontSize: 12,
                  padding: "4px 12px",
                  opacity: editContent.trim() ? 1 : 0.5,
                }}
              >
                Fork
              </button>
            </div>
          </div>
        ) : (
          message.content
        )}

        {/* Edit/fork button — user messages only, not pending/failed */}
        {isUser && !isEditing && !message.local_status && onFork && (
          <button
            onClick={handleEditStart}
            aria-label="Edit and fork from this message"
            className="bubble-edit-btn"
            style={{
              position: "absolute",
              top: 0,
              right: 44,
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              color: "var(--color-text-muted)",
              padding: "2px 6px",
              borderRadius: 4,
              minWidth: 44,
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            &#9998;
          </button>
        )}

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

        {isUser && message.local_status === "pending" && !isComposing && (
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
                padding: "4px 8px",
                minHeight: 44,
                display: "inline-flex",
                alignItems: "center",
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
