// src/stores/sessionStore.ts
import { create } from "zustand";
import type {
  Session,
  ChatMessage,
  CompositionState,
  CompositionStateVersion,
  ApiError,
  ValidationResult,
} from "@/types/api";
import * as api from "@/api/client";
import { COMPOSE_TIMEOUT_MS } from "@/config/composer";
import { useBlobStore } from "./blobStore";
import { useExecutionStore } from "./executionStore";

function getExecutionStore() {
  return useExecutionStore.getState();
}

interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  compositionState: CompositionState | null;
  isComposing: boolean;
  stateVersions: CompositionStateVersion[];
  error: string | null;

  // Shared selection state for cross-component sync (GraphView <-> SpecView)
  selectedNodeId: string | null;
  selectNode: (nodeId: string | null) => void;

  loadSessions: () => Promise<void>;
  createSession: () => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  archiveSession: (id: string) => Promise<void>;
  sendMessage: (content: string, signal?: AbortSignal) => Promise<void>;
  sendValidationFeedback: (result: ValidationResult) => Promise<void>;
  retryMessage: (messageId: string, signal?: AbortSignal) => Promise<void>;
  forkFromMessage: (messageId: string, newContent: string) => Promise<void>;
  loadStateVersions: () => Promise<void>;
  isLoadingVersions: boolean;
  revertToVersion: (stateId: string) => Promise<void>;
  clearError: () => void;
  injectSystemMessage: (content: string, stableId?: string) => void;
  reset: () => void;
}

const initialState = {
  sessions: [] as Session[],
  activeSessionId: null as string | null,
  messages: [] as ChatMessage[],
  compositionState: null as CompositionState | null,
  isComposing: false,
  stateVersions: [] as CompositionStateVersion[],
  isLoadingVersions: false,
  error: null as string | null,
  selectedNodeId: null as string | null,
};

export const useSessionStore = create<SessionState>((set, get) => ({
  ...initialState,

  async loadSessions() {
    try {
      const sessions = await api.fetchSessions();
      set({ sessions });
    } catch {
      set({ error: "Failed to load sessions. Please refresh the page." });
    }
  },

  async createSession() {
    try {
      const session = await api.createSession();
      set((state) => ({
        sessions: [session, ...state.sessions],
        activeSessionId: session.id,
        messages: [],
        compositionState: null,
        stateVersions: [],
        error: null,
        selectedNodeId: null, // Clear selection for new session
      }));
    } catch {
      set({ error: "Failed to create session. Please try again." });
    }
  },

  async archiveSession(id: string) {
    try {
      await api.archiveSession(id);
      set((state) => {
        const sessions = state.sessions.filter((s) => s.id !== id);
        // If we archived the active session, clear selection
        const wasActive = state.activeSessionId === id;
        return {
          sessions,
          ...(wasActive
            ? {
                activeSessionId: null,
                messages: [],
                compositionState: null,
                stateVersions: [],
                isComposing: false,
                selectedNodeId: null,
              }
            : {}),
        };
      });
    } catch {
      set({ error: "Failed to archive session. Please try again." });
    }
  },

  async selectSession(id: string) {
    // R4-H3: Clear validation when switching sessions to prevent
    // stale validation from a previous session being visible
    getExecutionStore().clearValidation();

    set({
      activeSessionId: id,
      messages: [],
      compositionState: null,
      stateVersions: [],
      isComposing: false,
      error: null,
      selectedNodeId: null, // Clear selection when switching sessions
    });

    try {
      const [messages, compositionState] = await Promise.all([
        api.fetchMessages(id),
        api.fetchCompositionState(id),
      ]);
      set({ messages, compositionState });

      // Fire-and-forget: refresh blob list for the newly selected session
      useBlobStore.getState().loadBlobs(id);
    } catch {
      set({ error: "Failed to load session. Please refresh the page." });
    }
  },

  async sendMessage(content: string, signal?: AbortSignal) {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    const optimisticMessage: ChatMessage = {
      id: `local-${crypto.randomUUID()}`,
      session_id: activeSessionId,
      role: "user",
      content,
      tool_calls: null,
      created_at: new Date().toISOString(),
      local_status: "pending",
    };

    set((state) => ({
      isComposing: true,
      error: null,
      messages: [...state.messages, optimisticMessage],
    }));

    try {
      const stateId = get().compositionState?.id;
      const result = await api.sendMessage(activeSessionId, content, stateId, signal);
      const { message, state } = result;
      set((s) => {
        const previousVersion = s.compositionState?.version ?? null;
        const newVersion = state?.version ?? null;
        const versionChanged =
          newVersion !== null && newVersion !== previousVersion;

        // R4-H3: Clear validation BEFORE updating compositionState
        // when a new state version arrives from the composer
        if (versionChanged) {
          getExecutionStore().clearValidation();
        }

        // Clear selection if the selected node no longer exists in new state
        const newState = state ?? s.compositionState;
        const nodeStillExists =
          !s.selectedNodeId ||
          newState?.nodes.some((n) => n.id === s.selectedNodeId);

        return {
          messages: s.messages.map((existing) =>
            existing.id === optimisticMessage.id
              ? { ...existing, local_status: undefined, local_error: undefined }
              : existing,
          ).concat(message),
          compositionState: newState,
          isComposing: false,
          ...(nodeStillExists ? {} : { selectedNodeId: null }),
        };
      });

      // Fire-and-forget: refresh blob list in case the LLM created files
      useBlobStore.getState().loadBlobs(activeSessionId);
    } catch (err) {
      const apiErr = err as ApiError;
      let errorMessage: string;
      // Error dispatch based on HTTP status + error_type field
      if (apiErr.status === 422 && apiErr.error_type === "convergence") {
        errorMessage =
          "ELSPETH couldn't complete the composition after multiple attempts. Try breaking your request into smaller steps.";
      } else if (
        apiErr.status === 502 &&
        apiErr.error_type === "llm_unavailable"
      ) {
        errorMessage =
          "The AI service is temporarily unavailable. Please try again in a moment.";
      } else if (
        apiErr.status === 502 &&
        apiErr.error_type === "llm_auth_error"
      ) {
        errorMessage =
          "The AI service configuration is invalid. Please contact your administrator.";
      } else {
        errorMessage =
          apiErr.detail ?? "Failed to send message. Please try again.";
      }
      set((state) => ({
        isComposing: false,
        error: errorMessage,
        messages: state.messages.map((existing) =>
          existing.id === optimisticMessage.id
            ? { ...existing, local_status: "failed", local_error: errorMessage }
            : existing,
        ),
      }));
    }
  },

  async sendValidationFeedback(result: ValidationResult) {
    // Format validation errors into a message the LLM can act on.
    const lines = ["Pipeline validation failed with the following errors:"];
    for (const err of result.errors) {
      lines.push(
        `- [${err.component_type ?? "unknown"}] ${err.component_id ?? "unknown"}: ${err.message}`,
      );
      if (err.suggestion) {
        lines.push(`  Suggestion: ${err.suggestion}`);
      }
    }
    lines.push("", "Please fix these validation errors.");
    const content = lines.join("\n");

    // Use sendMessage with the same timeout as manual sends.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), COMPOSE_TIMEOUT_MS);
    try {
      await get().sendMessage(content, controller.signal);
    } finally {
      clearTimeout(timer);
    }
  },

  async retryMessage(messageId: string, signal?: AbortSignal) {
    const { activeSessionId, messages } = get();
    if (!activeSessionId) return;

    const message = messages.find((entry) => entry.id === messageId);
    if (!message || message.role !== "user") return;

    set((state) => ({
      isComposing: true,
      error: null,
      messages: state.messages.map((existing) =>
        existing.id === messageId
          ? { ...existing, local_status: "pending" }
          : existing,
      ),
    }));

    try {
      // Use recompose (not sendMessage) — the user message is already
      // persisted from the original send. Calling sendMessage again
      // would insert a duplicate user message.
      const result = await api.recompose(activeSessionId, signal);
      const { message: assistantMessage, state } = result;
      set((s) => {
        const previousVersion = s.compositionState?.version ?? null;
        const newVersion = state?.version ?? null;
        const versionChanged =
          newVersion !== null && newVersion !== previousVersion;

        if (versionChanged) {
          getExecutionStore().clearValidation();
        }

        // Clear selection if the selected node no longer exists in new state
        const newState = state ?? s.compositionState;
        const nodeStillExists =
          !s.selectedNodeId ||
          newState?.nodes.some((n) => n.id === s.selectedNodeId);

        return {
          messages: s.messages.map((existing) =>
            existing.id === messageId
              ? { ...existing, local_status: undefined, local_error: undefined }
              : existing,
          ).concat(assistantMessage),
          compositionState: newState,
          isComposing: false,
          ...(nodeStillExists ? {} : { selectedNodeId: null }),
        };
      });

      // Fire-and-forget: refresh blob list in case the LLM created files
      useBlobStore.getState().loadBlobs(activeSessionId);
    } catch (err) {
      const apiErr = err as ApiError;
      const errorMessage =
        apiErr.status === 502 && apiErr.error_type === "llm_unavailable"
          ? "No LLM is available for the composer right now."
          : apiErr.status === 502 && apiErr.error_type === "llm_auth_error"
            ? "The AI service configuration is invalid. Please contact your administrator."
            : apiErr.status === 422 && apiErr.error_type === "convergence"
              ? "ELSPETH couldn't complete the composition after multiple attempts. Try breaking your request into smaller steps."
              : apiErr.detail ?? "Failed to send message. Please try again.";

      set((state) => ({
        isComposing: false,
        error: errorMessage,
        messages: state.messages.map((existing) =>
          existing.id === messageId
            ? { ...existing, local_status: "failed", local_error: errorMessage }
            : existing,
        ),
      }));
    }
  },

  async forkFromMessage(messageId: string, newContent: string) {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    set({ isComposing: true, error: null });
    try {
      const result = await api.forkFromMessage(
        activeSessionId,
        messageId,
        newContent,
      );
      // Clear validation for the new session
      getExecutionStore().clearValidation();

      set((state) => ({
        sessions: [result.session, ...state.sessions],
        activeSessionId: result.session.id,
        messages: result.messages,
        compositionState: result.composition_state,
        stateVersions: [],
        isComposing: false,
        selectedNodeId: null, // Clear selection for forked session
      }));

      // Fire-and-forget: refresh blob list for the NEW forked session
      useBlobStore.getState().loadBlobs(result.session.id);
    } catch {
      set({
        isComposing: false,
        error: "Failed to fork conversation. Please try again.",
      });
    }
  },

  async loadStateVersions() {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    set({ isLoadingVersions: true });
    try {
      const versions = await api.fetchStateVersions(activeSessionId);
      set({ stateVersions: versions, isLoadingVersions: false });
    } catch {
      // Version history is non-critical -- fail silently
      set({ isLoadingVersions: false });
    }
  },

  async revertToVersion(stateId: string) {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    try {
      // R4-H3: Clear validation BEFORE updating compositionState
      // to prevent a frame where stale validation is visible with the new version
      getExecutionStore().clearValidation();

      const compositionState = await api.revertToVersion(
        activeSessionId,
        stateId,
      );
      // Clear selection — the reverted version may not contain the selected node
      set({ compositionState, selectedNodeId: null });
    } catch {
      set({ error: "Failed to revert to version. Please try again." });
    }
  },

  clearError() {
    set({ error: null });
  },

  selectNode(nodeId: string | null) {
    set({ selectedNodeId: nodeId });
  },

  injectSystemMessage(content: string, stableId?: string) {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    const messageId = stableId ?? `system-${crypto.randomUUID()}`;

    const systemMessage: ChatMessage = {
      id: messageId,
      session_id: activeSessionId,
      role: "system",
      content,
      tool_calls: null,
      created_at: new Date().toISOString(),
    };

    set((state) => {
      // If a stable ID was provided, replace any existing message with
      // that ID instead of appending. This prevents noise accumulation
      // from repeated validation cycles.
      const filtered = stableId
        ? state.messages.filter((m) => m.id !== stableId)
        : state.messages;
      return { messages: [...filtered, systemMessage] };
    });
  },

  reset() {
    set(initialState);
  },
}));
