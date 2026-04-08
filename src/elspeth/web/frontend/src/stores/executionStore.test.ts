import { describe, it, expect, vi, beforeEach } from "vitest";
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
    useExecutionStore.getState().reset();
  });

  it("stores validation result on success", async () => {
    const result: ValidationResult = {
      is_valid: true,
      summary: "All checks passed",
      checks: [],
      errors: [],
      warnings: [],
    };

    const { validatePipeline } = await import("@/api/client");
    (validatePipeline as ReturnType<typeof vi.fn>).mockResolvedValue(result);

    await useExecutionStore.getState().validate("session-1");

    const state = useExecutionStore.getState();
    expect(state.validationResult).toEqual(result);
    expect(state.isValidating).toBe(false);
  });

  it("stores validation result on failure without side effects", async () => {
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

    await useExecutionStore.getState().validate("session-1");

    // validate() should only store the result — no cross-store side effects.
    // Orchestration (system messages, LLM feedback) is handled by InspectorPanel.
    const state = useExecutionStore.getState();
    expect(state.validationResult).toEqual(failedResult);
    expect(state.isValidating).toBe(false);
    expect(state.error).toBeNull();
  });

  it("sets error state when API call fails", async () => {
    const { validatePipeline } = await import("@/api/client");
    (validatePipeline as ReturnType<typeof vi.fn>).mockRejectedValue({
      status: 500,
      detail: "Internal server error",
    });

    await useExecutionStore.getState().validate("session-1");

    const state = useExecutionStore.getState();
    expect(state.validationResult).toBeNull();
    expect(state.isValidating).toBe(false);
    expect(state.error).toContain("internal error");
  });
});
