import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSessionStore } from "./sessionStore";
import { useExecutionStore } from "./executionStore";
import type { ValidationResult } from "@/types/index";

// Mock the API client
vi.mock("@/api/client", () => ({
  validatePipeline: vi.fn(),
  fetchRuns: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/websocket", () => ({
  connectToRun: vi.fn(),
}));

describe("executionStore.validate", () => {
  beforeEach(() => {
    useSessionStore.setState({
      activeSessionId: "session-1",
      messages: [],
      compositionState: null,
      isComposing: false,
      stateVersions: [],
      isLoadingVersions: false,
      error: null,
      sessions: [],
    });
    useExecutionStore.getState().reset();
  });

  it("injects a system message into chat when validation fails", async () => {
    const failedResult: ValidationResult = {
      is_valid: false,
      summary: "Validation failed",
      checks: [],
      errors: [
        {
          component_id: "llm_extract",
          component_type: "transform",
          message: "Missing required option: model",
          suggestion: "Add a model option",
        },
      ],
      warnings: [],
    };

    const { validatePipeline } = await import("@/api/client");
    (validatePipeline as ReturnType<typeof vi.fn>).mockResolvedValue(failedResult);

    // Spy on sendValidationFeedback to confirm it's still called
    const sendFeedback = vi.spyOn(useSessionStore.getState(), "sendValidationFeedback");

    await useExecutionStore.getState().validate("session-1");

    // A system message should have been injected
    const messages = useSessionStore.getState().messages;
    const systemMessages = messages.filter((m) => m.role === "system");
    expect(systemMessages.length).toBeGreaterThanOrEqual(1);
    expect(systemMessages[0].content).toContain("Validation failed");
    expect(systemMessages[0].content).toContain("llm_extract");

    // sendValidationFeedback should still be called (sends to LLM)
    expect(sendFeedback).toHaveBeenCalledWith(failedResult);
  });
});
