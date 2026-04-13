import { describe, it, expect, beforeEach, vi } from "vitest";
import { useSessionStore } from "./sessionStore";
import { resetStore } from "@/test/store-helpers";

// Mock the API client — store tests verify state logic, not HTTP calls
vi.mock("@/api/client", () => ({
  fetchSessions: vi.fn(),
  createSession: vi.fn(),
  fetchMessages: vi.fn(),
  fetchCompositionState: vi.fn(),
  sendMessage: vi.fn(),
  revertToVersion: vi.fn(),
  fetchStateVersions: vi.fn(),
  archiveSession: vi.fn(),
}));

// Mock the execution store dependency
vi.mock("./executionStore", () => ({
  useExecutionStore: {
    getState: () => ({ clearValidation: vi.fn() }),
  },
}));

describe("sessionStore", () => {
  beforeEach(() => {
    resetStore(useSessionStore);
  });

  describe("initial state", () => {
    it("starts with empty sessions and no active session", () => {
      const state = useSessionStore.getState();
      expect(state.sessions).toEqual([]);
      expect(state.activeSessionId).toBeNull();
      expect(state.messages).toEqual([]);
      expect(state.compositionState).toBeNull();
      expect(state.isComposing).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe("sendMessage optimistic insert", () => {
    it("appends optimistic user message and sets composing", async () => {
      // Pre-condition: set an active session so sendMessage proceeds
      useSessionStore.setState({ activeSessionId: "session-1" });

      // Start the send — it will await the mocked API call (which
      // returns undefined by default, causing the catch branch).
      // We only care about the intermediate optimistic state here.
      const sendPromise = useSessionStore.getState().sendMessage("hello");

      // After the synchronous part of sendMessage runs, check state
      const state = useSessionStore.getState();
      expect(state.isComposing).toBe(true);
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].role).toBe("user");
      expect(state.messages[0].content).toBe("hello");
      expect(state.messages[0].local_status).toBe("pending");

      // Let the promise settle (will hit error path since mock returns undefined)
      await sendPromise;
    });

    it("marks message as failed when API call throws", async () => {
      const { sendMessage: mockSendMessage } = await import("@/api/client");
      (mockSendMessage as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
        status: 500,
        detail: "Server error",
      });

      useSessionStore.setState({ activeSessionId: "session-1" });
      await useSessionStore.getState().sendMessage("hello");

      const state = useSessionStore.getState();
      expect(state.isComposing).toBe(false);
      expect(state.error).toBe("Server error");
      expect(state.messages[0].local_status).toBe("failed");
      expect(state.messages[0].local_error).toBe("Server error");
    });

    it("clears local_status on successful response", async () => {
      const { sendMessage: mockSendMessage } = await import("@/api/client");
      (mockSendMessage as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        message: {
          id: "asst-1",
          session_id: "session-1",
          role: "assistant",
          content: "Hello back",
          tool_calls: null,
          created_at: new Date().toISOString(),
        },
        state: null,
      });

      useSessionStore.setState({ activeSessionId: "session-1" });
      await useSessionStore.getState().sendMessage("hello");

      const state = useSessionStore.getState();
      expect(state.isComposing).toBe(false);
      // User message should have local_status cleared
      const userMsg = state.messages.find((m) => m.role === "user");
      expect(userMsg?.local_status).toBeUndefined();
      // Assistant message should be appended
      const asstMsg = state.messages.find((m) => m.role === "assistant");
      expect(asstMsg?.content).toBe("Hello back");
    });

    it("handles convergence error with specific message", async () => {
      const { sendMessage: mockSendMessage } = await import("@/api/client");
      (mockSendMessage as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
        status: 422,
        error_type: "convergence",
        detail: "ignored",
      });

      useSessionStore.setState({ activeSessionId: "session-1" });
      await useSessionStore.getState().sendMessage("hello");

      const state = useSessionStore.getState();
      expect(state.error).toContain("couldn't complete the composition");
    });
  });

  describe("reset", () => {
    it("restores initial state", () => {
      useSessionStore.setState({
        activeSessionId: "session-1",
        isComposing: true,
        error: "some error",
      });

      useSessionStore.getState().reset();

      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBeNull();
      expect(state.isComposing).toBe(false);
      expect(state.error).toBeNull();
    });
  });
});
