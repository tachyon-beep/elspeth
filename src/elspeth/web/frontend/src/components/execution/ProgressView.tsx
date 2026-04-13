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

import { useState } from "react";
import { useExecutionStore } from "@/stores/executionStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

export function ProgressView() {
  const { progress, wsDisconnected, activeRunId } = useWebSocket();
  const cancel = useExecutionStore((s) => s.cancel);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  if (!progress || !activeRunId) return null;

  const isTerminal =
    progress.status === "completed" || progress.status === "cancelled";

  return (
    <div className="progress-container">
      {/* WebSocket disconnect banner */}
      {wsDisconnected && !isTerminal && (
        <div
          role="status"
          className="progress-ws-banner"
        >
          Live progress connection lost. Reconnecting...
        </div>
      )}

      {/* Status header with cancel button */}
      <div className="progress-status-header">
        <span className="progress-status-label">
          {progress.status}
        </span>
        {!isTerminal && (
          <button
            onClick={() => setShowCancelConfirm(true)}
            aria-label="Cancel pipeline execution"
            className="btn btn-danger progress-cancel-btn"
          >
            Cancel
          </button>
        )}
      </div>

      {showCancelConfirm && (
        <ConfirmDialog
          title="Cancel pipeline"
          message="Cancel the running pipeline? This cannot be undone."
          confirmLabel="Cancel pipeline"
          variant="danger"
          onConfirm={() => {
            cancel(activeRunId);
            setShowCancelConfirm(false);
          }}
          onCancel={() => setShowCancelConfirm(false)}
        />
      )}

      {/* Progress bar -- indeterminate mode (no percentage, animated stripe) */}
      <div
        className="progress-bar progress-bar-outer"
        role="progressbar"
        aria-label="Pipeline execution in progress"
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
      <div className="progress-counters">
        <div>
          <div className="progress-counter-label">
            Processed
          </div>
          <div className="progress-counter-value">
            {progress.rows_processed.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="progress-counter-label">
            Failed
          </div>
          <div
            className="progress-counter-value"
            style={{
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
          className="progress-cancelled-msg"
        >
          Pipeline execution was cancelled.
        </div>
      )}

      {/* Recent errors */}
      {progress.recent_errors.length > 0 && (
        <div>
          <div className="progress-errors-title">
            Recent errors ({progress.recent_errors.length})
          </div>
          <div className="progress-errors-container">
            {progress.recent_errors.map((err, i) => (
              <div
                key={`${err.node_id}-${i}`}
                className="progress-error-item"
                style={{
                  borderBottom:
                    i < progress.recent_errors.length - 1
                      ? "1px solid var(--color-error-border)"
                      : "none",
                }}
              >
                {err.node_id && <strong>{err.node_id}</strong>}
                {err.node_id && ": "}
                {err.message}
                {err.row_id && (
                  <span className="progress-error-row-id">
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
