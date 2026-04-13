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
      className="composing-indicator composing-row"
      aria-live="polite"
      role="status"
    >
      <div className="composing-bubble">
        <span className="composing-dot" aria-hidden="true" />
        <span className="composing-dot" aria-hidden="true" />
        <span className="composing-dot" aria-hidden="true" />
        <span className="composing-text">
          ELSPETH is composing...
        </span>
      </div>
    </div>
  );
}
