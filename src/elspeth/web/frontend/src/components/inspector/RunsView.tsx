// ============================================================================
// RunsView
//
// List of runs for the current session. Each run entry shows:
// - Status badge (colour + text label, not colour alone)
// - Row counts (rows_processed, rows_failed)
// - Duration (elapsed time or "running..." for active runs)
// - Composition state version
//
// Click an active run to expand and show ProgressView inline.
//
// Empty state: "No runs yet. Validate your pipeline, then click Execute
// to run it."
// ============================================================================

import { useEffect } from "react";
import { useExecutionStore } from "@/stores/executionStore";
import { useSessionStore } from "@/stores/sessionStore";
import { ProgressView } from "@/components/execution/ProgressView";
import type { Run } from "@/types/index";

// ── Status badge CSS class mapping ───────────────────────────────────────────
// Uses .status-badge + .status-badge-{status} classes from App.css

const STATUS_BADGE_CLASSES: Record<Run["status"], string> = {
  pending: "status-badge status-badge-pending",
  running: "status-badge status-badge-running",
  completed: "status-badge status-badge-completed",
  failed: "status-badge status-badge-failed",
  cancelled: "status-badge status-badge-cancelled",
};

// ── Duration formatting ──────────────────────────────────────────────────────

function formatDuration(startedAt: string, finishedAt: string | null): string {
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const diffSec = Math.floor((end - start) / 1000);

  if (diffSec < 60) return `${diffSec}s`;
  const min = Math.floor(diffSec / 60);
  const sec = diffSec % 60;
  return `${min}m ${sec}s`;
}

// ── RunsView component ───────────────────────────────────────────────────────

export function RunsView() {
  const runs = useExecutionStore((s) => s.runs);
  const activeRunId = useExecutionStore((s) => s.activeRunId);
  const progress = useExecutionStore((s) => s.progress);
  const loadRuns = useExecutionStore((s) => s.loadRuns);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);

  // Load runs when the view mounts or session changes
  useEffect(() => {
    if (activeSessionId) {
      loadRuns(activeSessionId);
    }
  }, [activeSessionId, loadRuns]);

  // Empty state
  if (runs.length === 0) {
    return (
      <div
        className="empty-state"
        style={{
          padding: 24,
          fontSize: 14,
        }}
      >
        No runs yet. Validate your pipeline, then click Execute to run it.
      </div>
    );
  }

  return (
    <div style={{ padding: 8 }}>
      {runs.map((run) => {
        const isActive =
          run.id === activeRunId && progress?.status === "running";

        return (
          <div key={run.id}>
            <div
              className="component-card"
              style={{
                padding: "10px 12px",
                marginBottom: 4,
                fontSize: 13,
              }}
            >
              {/* Top row: status badge + version */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 4,
                }}
              >
                {/* Status badge: uses CSS class from App.css */}
                <span className={STATUS_BADGE_CLASSES[run.status]}>
                  {run.status}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--color-text-muted)",
                  }}
                >
                  v{run.composition_version}
                </span>
              </div>

              {/* Row counts + duration */}
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  fontSize: 12,
                  color: "var(--color-text-muted)",
                }}
              >
                <span>
                  {run.rows_processed.toLocaleString()} rows
                  {run.rows_failed > 0 && (
                    <span style={{ color: "var(--color-error)" }}>
                      {" "}
                      ({run.rows_failed.toLocaleString()} failed)
                    </span>
                  )}
                </span>
                <span>
                  {run.status === "running"
                    ? "running..."
                    : formatDuration(run.started_at, run.finished_at)}
                </span>
              </div>
            </div>

            {/* Show live progress inline for the active running run */}
            {isActive && <ProgressView />}
          </div>
        );
      })}
    </div>
  );
}
