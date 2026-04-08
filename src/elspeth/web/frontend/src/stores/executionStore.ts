// ============================================================================
// ELSPETH Execution Store
//
// Zustand store managing validation results, execution runs, live progress,
// and the WebSocket connection lifecycle.
//
// Key behaviour: auto-clear. When the session store's compositionState.version
// changes, the validation result is cleared and the Execute button becomes
// disabled. This is implemented via a cross-store subscription initialised
// in stores/subscriptions.ts (called once from App.tsx at startup).
// ============================================================================

import { create } from "zustand";
import type {
  Run,
  RunProgress,
  RunEvent,
  RunEventProgress,
  RunEventError,
  RunEventCompleted,
  RunEventCancelled,
  RunEventFailed,
  ValidationResult,
  ApiError,
} from "@/types/index";
import * as api from "@/api/client";
import { connectToRun, type WebSocketConnection } from "@/api/websocket";
import { useAuthStore } from "./authStore";


const MAX_RECENT_ERRORS = 50;

interface ExecutionState {
  runs: Run[];
  activeRunId: string | null;
  progress: RunProgress | null;
  validationResult: ValidationResult | null;
  isValidating: boolean;
  isExecuting: boolean;
  wsDisconnected: boolean;
  error: string | null;

  validate: (sessionId: string) => Promise<void>;
  execute: (sessionId: string) => Promise<void>;
  cancel: (runId: string) => Promise<void>;
  loadRuns: (sessionId: string) => Promise<void>;
  connectWebSocket: (runId: string) => void;
  clearValidation: () => void;
  reset: () => void;
}

// The WebSocket connection handle is held outside Zustand state
// because it's not serialisable and components don't need to read it.
let wsConnection: WebSocketConnection | null = null;

/**
 * Apply a RunEvent to the current progress state.
 * Accumulates exceptions (keeping the most recent N) and updates
 * row counters. Terminal events ("completed", "cancelled") update
 * the run status in the runs list.
 */
function applyRunEvent(
  state: ExecutionState,
  event: RunEvent,
): Partial<ExecutionState> {
  const data = event.data;

  // Accumulate errors for "error" events, keeping the most recent N.
  // New errors come first (newest-first display).
  const newErrors =
    event.event_type === "error"
      ? [data as RunEventError, ...(state.progress?.recent_errors ?? [])]
      : [...(state.progress?.recent_errors ?? [])];
  const recentErrors = newErrors.slice(0, MAX_RECENT_ERRORS);

  // Extract row counts from data payload (progress, completed, cancelled all have them)
  const rowsProcessed =
    "rows_processed" in data ? (data as RunEventProgress).rows_processed : (state.progress?.rows_processed ?? 0);
  const rowsFailed =
    "rows_failed" in data ? (data as RunEventProgress).rows_failed : (state.progress?.rows_failed ?? 0);

  const newProgress: RunProgress = {
    rows_processed: rowsProcessed,
    rows_failed: rowsFailed,
    recent_errors: recentErrors,
    // "error" is non-terminal (per-row exception) -- status stays "running"
    status:
      event.event_type === "completed"
        ? "completed"
        : event.event_type === "cancelled"
          ? "cancelled"
          : event.event_type === "failed"
            ? "failed"
            : "running",
  };

  // Update the run in the list when terminal.
  // "error" is non-terminal -- "completed", "cancelled", and "failed" are terminal.
  let updatedRuns = state.runs;
  if (event.event_type === "completed" || event.event_type === "cancelled" || event.event_type === "failed") {
    updatedRuns = state.runs.map((r) =>
      r.id === event.run_id
        ? {
            ...r,
            status: newProgress.status as Run["status"],
            rows_processed: rowsProcessed,
            rows_failed: rowsFailed,
          }
        : r,
    );
  }

  return {
    progress: newProgress,
    runs: updatedRuns,
    wsDisconnected: false,
  };
}

const initialExecutionState = {
  runs: [] as Run[],
  activeRunId: null as string | null,
  progress: null as RunProgress | null,
  validationResult: null as ValidationResult | null,
  isValidating: false,
  isExecuting: false,
  wsDisconnected: false,
  error: null as string | null,
};

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  ...initialExecutionState,

  async validate(sessionId: string) {
    set({ isValidating: true, validationResult: null, error: null });
    try {
      const result = await api.validatePipeline(sessionId);
      set({ validationResult: result, isValidating: false });
    } catch (err) {
      const apiErr = err as ApiError;
      const message =
        apiErr.status === 500
          ? "Validation encountered an internal error. Please try again."
          : apiErr.detail ?? "Validation failed. Please try again.";
      set({
        isValidating: false,
        error: message,
      });
    }
  },

  async execute(sessionId: string) {
    set({ isExecuting: true, error: null });
    try {
      const { run_id } = await api.executePipeline(sessionId);
      set({
        activeRunId: run_id,
        isExecuting: false,
        progress: {
          rows_processed: 0,
          rows_failed: 0,
          recent_errors: [],
          status: "running",
        },
      });

      // Refresh runs list so the new run appears in the Runs tab immediately
      get().loadRuns(sessionId);

      // Connect WebSocket for live progress
      get().connectWebSocket(run_id);
    } catch (err) {
      const apiErr = err as ApiError;
      const message =
        apiErr.status === 409
          ? "A run is already in progress for this pipeline."
          : apiErr.detail ??
            "Pipeline execution failed. Check the Runs tab for error details.";
      set({
        isExecuting: false,
        error: message,
      });
    }
  },

  connectWebSocket(runId: string) {
    // Close any existing WebSocket connection
    wsConnection?.close();

    // Open a WebSocket for live progress, passing JWT as query parameter
    const token = useAuthStore.getState().token ?? "";
    wsConnection = connectToRun(runId, token, {
      onProgress(event: RunEvent, _data: RunEventProgress) {
        set((state) => applyRunEvent(state, event));
      },
      onError(event: RunEvent, _data: RunEventError) {
        // Non-terminal: per-row exception. Accumulate into progress.
        set((state) => applyRunEvent(state, event));
      },
      onComplete(event: RunEvent, _data: RunEventCompleted) {
        set((state) => applyRunEvent(state, event));
      },
      onCancelled(event: RunEvent, _data: RunEventCancelled) {
        set((state) => applyRunEvent(state, event));
      },
      onFailed(event: RunEvent, _data: RunEventFailed) {
        set((state) => applyRunEvent(state, event));
      },
      onAuthFailure() {
        // Close code 4001 -- do not reconnect, trigger logout
        useAuthStore.getState().logout();
      },
    });
  },

  async cancel(runId: string) {
    try {
      await api.cancelRun(runId);
    } catch (err) {
      const apiErr = err as ApiError;
      set({ error: apiErr.detail ?? "Failed to cancel run." });
    }
  },

  async loadRuns(sessionId: string) {
    try {
      const runs = await api.fetchRuns(sessionId);
      set({ runs });
    } catch {
      // Non-critical -- runs list can be stale temporarily
    }
  },

  clearValidation() {
    set({ validationResult: null });
  },

  reset() {
    wsConnection?.close();
    wsConnection = null;
    set(initialExecutionState);
  },
}));
