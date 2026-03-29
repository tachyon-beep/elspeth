// ============================================================================
// ProgressView
//
// Live progress display for an active execution run. Shows:
// - Indeterminate progress bar (using .progress-bar CSS classes from App.css)
// - Row counters: rows_processed, rows_failed (large, prominent)
// - Recent errors list (scrolling, newest first, capped at 50)
// - Cancel button (disabled once run reaches terminal state)
// - "Pipeline execution was cancelled" message on cancelled event
// - WebSocket disconnect banner with reconnect status
// ============================================================================

import { useExecutionStore } from "@/stores/executionStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function ProgressView() {
  const { progress, wsDisconnected, activeRunId } = useWebSocket();
  const cancel = useExecutionStore((s) => s.cancel);

  if (!progress || !activeRunId) return null;

  const isTerminal =
    progress.status === "completed" || progress.status === "cancelled";

  return (
    <div style={{ padding: 12, fontSize: 13 }}>
      {/* WebSocket disconnect banner */}
      {wsDisconnected && !isTerminal && (
        <div
          role="status"
          style={{
            padding: "6px 10px",
            marginBottom: 8,
            backgroundColor: "rgba(255, 204, 102, 0.15)",
            color: "var(--color-warning)",
            border: "1px solid rgba(255, 204, 102, 0.3)",
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          Live progress connection lost. Reconnecting...
        </div>
      )}

      {/* Status header with cancel button */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <span
          style={{
            fontWeight: 600,
            textTransform: "uppercase",
            fontSize: 12,
            color: "var(--color-text)",
          }}
        >
          {progress.status}
        </span>
        {!isTerminal && (
          <button
            onClick={() => {
              if (window.confirm("Cancel the running pipeline? This cannot be undone.")) {
                cancel(activeRunId);
              }
            }}
            aria-label="Cancel pipeline execution"
            className="btn btn-danger"
            style={{
              padding: "4px 10px",
              fontSize: 12,
            }}
          >
            Cancel
          </button>
        )}
      </div>

      {/* Progress bar -- indeterminate mode (no percentage, animated stripe) */}
      <div
        className="progress-bar"
        role="progressbar"
        aria-label="Pipeline execution in progress"
        style={{
          height: 8,
          borderRadius: 4,
          marginBottom: 12,
        }}
      >
        <div
          className={isTerminal ? "progress-bar-complete" : "progress-bar-stripe"}
          style={
            isTerminal
              ? {
                  backgroundColor:
                    progress.status === "completed"
                      ? "var(--color-success)"
                      : "var(--color-warning)",
                }
              : {}
          }
        />
      </div>

      {/* Row counters -- large and prominent */}
      <div
        style={{
          display: "flex",
          gap: 24,
          marginBottom: 12,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              color: "var(--color-text-muted)",
              marginBottom: 2,
            }}
          >
            Processed
          </div>
          <div
            style={{
              fontSize: 20,
              fontWeight: 700,
              color: "var(--color-text)",
            }}
          >
            {progress.rows_processed.toLocaleString()}
          </div>
        </div>
        <div>
          <div
            style={{
              fontSize: 11,
              color: "var(--color-text-muted)",
              marginBottom: 2,
            }}
          >
            Failed
          </div>
          <div
            style={{
              fontSize: 20,
              fontWeight: 700,
              color:
                progress.rows_failed > 0
                  ? "var(--color-error)"
                  : "var(--color-text)",
            }}
          >
            {progress.rows_failed.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Cancellation message */}
      {progress.status === "cancelled" && (
        <div
          role="status"
          style={{
            padding: "8px 12px",
            marginBottom: 8,
            backgroundColor: "rgba(255, 204, 102, 0.15)",
            color: "var(--color-warning)",
            borderRadius: 4,
            fontSize: 13,
            border: "1px solid rgba(255, 204, 102, 0.3)",
          }}
        >
          Pipeline execution was cancelled.
        </div>
      )}

      {/* Recent errors */}
      {progress.recent_errors.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--color-error)",
              marginBottom: 4,
            }}
          >
            Recent errors ({progress.recent_errors.length})
          </div>
          <div
            style={{
              maxHeight: 200,
              overflowY: "auto",
              fontSize: 11,
              fontFamily: "var(--font-mono)",
              backgroundColor: "rgba(255, 102, 102, 0.12)",
              borderRadius: 4,
              padding: 8,
              border: "1px solid rgba(255, 102, 102, 0.3)",
            }}
          >
            {progress.recent_errors.map((err, i) => (
              <div
                key={`${err.node_id}-${i}`}
                style={{
                  marginBottom: 4,
                  paddingBottom: 4,
                  borderBottom:
                    i < progress.recent_errors.length - 1
                      ? "1px solid rgba(255, 102, 102, 0.2)"
                      : "none",
                }}
              >
                {err.node_id && <strong>{err.node_id}</strong>}
                {err.node_id && ": "}
                {err.message}
                {err.row_id && (
                  <span style={{ color: "var(--color-text-muted)" }}>
                    {" "}
                    (row: {err.row_id})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
