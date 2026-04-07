// src/components/chat/ChatInput.tsx
import {
  useState,
  useCallback,
  useRef,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useBlobStore } from "@/stores/blobStore";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  onToggleBlobManager?: () => void;
  showBlobManager?: boolean;
}

export function ChatInput({ onSend, disabled, inputRef, onToggleBlobManager, showBlobManager }: ChatInputProps) {
  const [text, setText] = useState("");
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const uploadBlob = useBlobStore((s) => s.uploadBlob);

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

    setUploadStatus(null);
    try {
      const blob = await uploadBlob(activeSessionId, file);
      // Reference blob by filename, not by filesystem path
      setText(
        (prev) =>
          prev +
          (prev ? "\n" : "") +
          `I've uploaded "${blob.filename}"; please use it as the pipeline input.`,
      );
    } catch {
      // Error is shown in the blob store / blob manager
      setUploadStatus("Upload failed. Check the file manager for details.");
    } finally {
      // Reset the file input so the same file can be re-selected
      const input = e.target;
      input.value = "";
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
      {uploadStatus && (
        <div
          role="alert"
          style={{
            padding: "6px 10px",
            marginBottom: 8,
            backgroundColor: "var(--color-error-bg)",
            color: "var(--color-error)",
            borderRadius: 4,
            fontSize: 12,
            border: "1px solid var(--color-error-border)",
          }}
        >
          {uploadStatus}
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

        {/* File manager toggle */}
        {onToggleBlobManager && (
          <button
            onClick={onToggleBlobManager}
            title={showBlobManager ? "Hide file manager" : "Show file manager"}
            aria-label={showBlobManager ? "Hide file manager" : "Show file manager"}
            style={{
              padding: "8px 10px",
              backgroundColor: showBlobManager
                ? "var(--color-surface-hover)"
                : "transparent",
              border: "1px solid var(--color-border-strong)",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 16,
              color: "var(--color-text)",
              minWidth: 44,
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span aria-hidden="true">{"\uD83D\uDCC1"}</span>
          </button>
        )}

        {/* File upload button — using a visible button that clicks a hidden input */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={!activeSessionId}
          style={{
            padding: "8px 10px",
            backgroundColor: "transparent",
            border: "1px solid var(--color-border-strong)",
            borderRadius: 6,
            cursor: !activeSessionId ? "not-allowed" : "pointer",
            fontSize: 16,
            color: "var(--color-text)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minWidth: 44,
            minHeight: 44,
          }}
          title="Upload file"
          aria-label="Upload file"
        >
          <span aria-hidden="true">{"\uD83D\uDCCE"}</span>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileSelect}
          disabled={!activeSessionId}
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
              ? "var(--color-accent)"
              : "var(--color-surface-elevated)",
            color: canSend
              ? "var(--color-text-inverse)"
              : "var(--color-text-muted)",
            border: "none",
            borderRadius: 6,
            cursor: canSend ? "pointer" : "not-allowed",
            fontSize: 14,
            minWidth: 44,
            minHeight: 44,
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
