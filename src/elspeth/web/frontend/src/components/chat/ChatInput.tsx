// src/components/chat/ChatInput.tsx
import {
  useState,
  useRef,
  useCallback,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import * as api from "@/api/client";
import type { ApiError } from "@/types/api";
import { useSessionStore } from "@/stores/sessionStore";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement>;
}

export function ChatInput({ onSend, disabled, inputRef }: ChatInputProps) {
  const [text, setText] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }, [text, disabled, onSend]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !activeSessionId) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const result = await api.uploadFile(activeSessionId, file);
      setText(
        (prev) =>
          prev +
          (prev ? "\n" : "") +
          `I've uploaded a file at ${result.path}`,
      );
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.status === 413) {
        setUploadError(
          "The file exceeds the maximum upload size. Please use a smaller file.",
        );
      } else {
        setUploadError(
          "Upload failed due to a network error. Please check your connection and try again.",
        );
      }
    } finally {
      setIsUploading(false);
      // Reset the file input so the same file can be re-selected
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  const canSend = !disabled && text.trim().length > 0;

  return (
    <div
      className="chat-input"
      style={{
        padding: "8px 16px",
        borderTop: "1px solid var(--color-border)",
      }}
    >
      {uploadError && (
        <div
          role="alert"
          style={{
            padding: "6px 10px",
            marginBottom: 8,
            backgroundColor: "rgba(255, 102, 102, 0.12)",
            color: "var(--color-error)",
            borderRadius: 4,
            fontSize: 12,
            border: "1px solid rgba(255, 102, 102, 0.3)",
          }}
        >
          {uploadError}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }} role="group" aria-label="Message composition">
        <textarea
          ref={inputRef}
          data-chat-input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe the pipeline you want to build..."
          aria-label="Message input"
          rows={2}
          style={{
            flex: 1,
            resize: "vertical",
            padding: "8px 12px",
            border: "1px solid var(--color-border-strong)",
            borderRadius: 6,
            fontSize: 14,
            fontFamily: "inherit",
            lineHeight: 1.4,
            backgroundColor: "var(--color-surface-elevated)",
            color: "var(--color-text)",
          }}
        />

        {/* File upload button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading || !activeSessionId}
          title="Upload file"
          aria-label="Upload file"
          style={{
            padding: "8px 10px",
            backgroundColor: "transparent",
            border: "1px solid var(--color-border-strong)",
            borderRadius: 6,
            cursor:
              isUploading || !activeSessionId ? "not-allowed" : "pointer",
            fontSize: 16,
            color: "var(--color-text)",
          }}
        >
          {isUploading ? (
            <span aria-hidden="true">&#9203;</span>
          ) : (
            <><span aria-hidden="true">&#128206;</span><span className="sr-only">Attach file</span></>
          )}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileSelect}
          style={{ display: "none" }}
          aria-hidden="true"
          tabIndex={-1}
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          style={{
            padding: "8px 16px",
            backgroundColor: canSend
              ? "var(--color-focus-ring)"
              : "var(--color-text-muted)",
            color: "var(--color-text)",
            border: "none",
            borderRadius: 6,
            cursor: canSend ? "pointer" : "not-allowed",
            fontSize: 14,
          }}
        >
          Send
        </button>
      </div>
      <div
        style={{
          fontSize: 11,
          color: "var(--color-text-muted)",
          padding: "2px 0 4px",
          textAlign: "right",
        }}
        aria-hidden="true"
      >
        Shift+Enter for new line
      </div>
    </div>
  );
}
