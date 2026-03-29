// src/components/chat/ComposingIndicator.tsx

/**
 * Animated three-dot composing indicator shown while the backend
 * is processing the LLM tool-use loop. Uses the .composing-dot CSS
 * class from App.css for staggered bounce animation.
 * Announces to screen readers via aria-live.
 */
export function ComposingIndicator() {
  return (
    <div
      className="composing-indicator"
      style={{
        display: "flex",
        justifyContent: "flex-start",
        padding: "4px 16px",
      }}
      aria-live="polite"
      role="status"
    >
      <div
        style={{
          padding: "10px 14px",
          borderRadius: 12,
          backgroundColor: "var(--color-bubble-assistant)",
          border: "1px solid var(--color-bubble-assistant-border)",
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <span className="composing-dot" aria-hidden="true" />
        <span className="composing-dot" aria-hidden="true" />
        <span className="composing-dot" aria-hidden="true" />
        <span
          style={{
            fontSize: 12,
            color: "var(--color-text-muted)",
            marginLeft: 6,
          }}
        >
          ELSPETH is composing...
        </span>
      </div>
    </div>
  );
}
