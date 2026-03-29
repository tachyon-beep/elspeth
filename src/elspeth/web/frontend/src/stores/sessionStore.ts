// src/stores/sessionStore.ts
import { create } from "zustand";
import type {
  Session,
  ChatMessage,
  CompositionState,
  CompositionStateVersion,
  ApiError,
} from "@/types/api";
import * as api from "@/api/client";
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

  loadSessions: () => Promise<void>;
  createSession: () => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  archiveSession: (id: string) => Promise<void>;
  sendMessage: (content: string, signal?: AbortSignal) => Promise<void>;
  retryMessage: (messageId: string, signal?: AbortSignal) => Promise<void>;
  loadStateVersions: () => Promise<void>;
  isLoadingVersions: boolean;
  revertToVersion: (stateId: string) => Promise<void>;
  clearError: () => void;
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
    });

    try {
      const [messages, compositionState] = await Promise.all([
        api.fetchMessages(id),
        api.fetchCompositionState(id),
      ]);
      set({ messages, compositionState });
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
      const result = await api.sendMessage(activeSessionId, content, signal);
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

        return {
          messages: s.messages.map((existing) =>
            existing.id === optimisticMessage.id
              ? { ...existing, local_status: undefined }
              : existing,
          ).concat(message),
          compositionState: state ?? s.compositionState,
          isComposing: false,
        };
      });
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
            ? { ...existing, local_status: "failed" }
            : existing,
        ),
      }));
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
      const result = await api.sendMessage(activeSessionId, message.content, signal);
      const { message: assistantMessage, state } = result;
      set((s) => {
        const previousVersion = s.compositionState?.version ?? null;
        const newVersion = state?.version ?? null;
        const versionChanged =
          newVersion !== null && newVersion !== previousVersion;

        if (versionChanged) {
          getExecutionStore().clearValidation();
        }

        return {
          messages: s.messages.map((existing) =>
            existing.id === messageId
              ? { ...existing, local_status: undefined }
              : existing,
          ).concat(assistantMessage),
          compositionState: state ?? s.compositionState,
          isComposing: false,
        };
      });
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
            ? { ...existing, local_status: "failed" }
            : existing,
        ),
      }));
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
      set({ compositionState });
    } catch {
      set({ error: "Failed to revert to version. Please try again." });
    }
  },

  clearError() {
    set({ error: null });
  },

  reset() {
    set(initialState);
  },
}));
