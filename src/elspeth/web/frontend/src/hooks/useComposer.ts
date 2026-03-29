// src/hooks/useComposer.ts
import { useCallback, useState } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import type { ApiError } from "@/types/api";

const COMPOSE_TIMEOUT_MS = 90_000;

/** Type guard for ApiError — ensures the cast is safe before accessing fields. */
function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    typeof (err as Record<string, unknown>).status === "number"
  );
}

/**
 * Map backend error responses to user-facing messages.
 * R4-M2: Checks error_type first, then HTTP status, then detail text.
 */
function dispatchComposerError(err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") {
    return "The composition request timed out. Try a simpler request.";
  }

  if (!isApiError(err)) {
    return "Failed to send message. Please try again.";
  }

  // error_type takes precedence (most specific signal)
  if (err.status === 422 && err.error_type === "convergence") {
    return "ELSPETH couldn't complete the composition after multiple attempts. Try breaking your request into smaller steps.";
  }
  if (err.status === 502 && err.error_type === "llm_unavailable") {
    return "The AI service is temporarily unavailable. Please try again in a moment.";
  }
  if (err.status === 502 && err.error_type === "llm_auth_error") {
    return "The AI service configuration is invalid. Please contact your administrator.";
  }
  return err.detail ?? "Failed to send message. Please try again.";
}

/**
 * Hook for composing messages. Wraps sessionStore.sendMessage()
 * with a 90-second AbortController timeout. Dispatches error messages
 * based on HTTP status and error_type field.
 *
 * The AbortController is wired to abort the underlying fetch when the
 * timeout fires. The sessionStore.sendMessage() call rejects with an
 * AbortError which is then mapped to the timeout user-facing message.
 */
export function useComposer() {
  const storeSendMessage = useSessionStore((s) => s.sendMessage);
  const isComposing = useSessionStore((s) => s.isComposing);
  const compositionState = useSessionStore((s) => s.compositionState);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      setError(null);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), COMPOSE_TIMEOUT_MS);
      try {
        await storeSendMessage(content, controller.signal);
      } catch (err) {
        setError(dispatchComposerError(err));
      } finally {
        clearTimeout(timer);
      }
    },
    [storeSendMessage],
  );

  return { sendMessage, isComposing, compositionState, error };
}
