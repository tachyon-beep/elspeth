// src/components/chat/ChatPanel.tsx
import { useEffect, useRef, useCallback } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useComposer } from "@/hooks/useComposer";
import { MessageBubble } from "./MessageBubble";
import { ComposingIndicator } from "./ComposingIndicator";
import { ChatInput } from "./ChatInput";

/**
 * Main chat panel combining the message list, composing indicator, and input.
 *
 * Auto-scrolls to the bottom on new messages unless the user has scrolled up.
 * Focus returns to the ChatInput textarea after the assistant response arrives.
 */
export function ChatPanel() {
  const messages = useSessionStore((s) => s.messages);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const clearError = useSessionStore((s) => s.clearError);
  const { sendMessage, isComposing, error } = useComposer();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isUserScrolledUp = useRef(false);

  // Track whether the user has scrolled up from the bottom
  function handleScroll() {
    const container = scrollContainerRef.current;
    if (!container) return;
    const threshold = 40; // pixels from bottom
    const atBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      threshold;
    isUserScrolledUp.current = !atBottom;
  }

  // Auto-scroll to bottom when new messages arrive (unless user scrolled up)
  useEffect(() => {
    if (!isUserScrolledUp.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isComposing]);

  // Return focus to input when composing ends (assistant response arrived)
  useEffect(() => {
    if (!isComposing) {
      inputRef.current?.focus();
    }
  }, [isComposing]);

  const handleSend = useCallback(
    (content: string) => {
      sendMessage(content);
    },
    [sendMessage],
  );

  // No active session: show prompt to select or create one
  if (!activeSessionId) {
    return (
      <div
        id="chat-main"
        className="chat-panel chat-panel--empty"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          color: "var(--color-text-muted)",
          fontSize: 15,
          padding: 32,
          textAlign: "center",
        }}
        role="main"
        aria-label="Chat panel"
      >
        Select a session from the sidebar, or create a new one to get
        started.
      </div>
    );
  }

  return (
    <div
      id="chat-main"
      className="chat-panel"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
      role="main"
      aria-label="Chat panel"
    >
      {/* Error banner */}
      {error && (
        <div
          role="alert"
          style={{
            padding: "8px 12px",
            backgroundColor: "rgba(255, 102, 102, 0.12)",
            color: "var(--color-error)",
            fontSize: 13,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{error}</span>
          <button
            onClick={clearError}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 16,
              color: "var(--color-error)",
              minWidth: 44,
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            aria-label="Dismiss error"
          >
            {"\u00D7"}
          </button>
        </div>
      )}

      {/* Message list */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: "auto", padding: "16px 0" }}
        role="log"
        aria-label="Chat messages"
        aria-live="polite"
        aria-relevant="additions"
      >
        {messages.length === 0 ? (
          <div
            style={{
              padding: 32,
              color: "var(--color-text-muted)",
              fontSize: 15,
              textAlign: "center",
            }}
          >
            Welcome to ELSPETH. Describe the pipeline you want to build,
            and I'll compose it for you.
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))
        )}
        {isComposing && <ComposingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        disabled={isComposing}
        inputRef={inputRef}
      />
    </div>
  );
}
