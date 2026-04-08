// src/components/blobs/BlobRow.tsx
import { useState } from "react";
import { previewBlobContent } from "@/api/client";
import type { BlobMetadata } from "@/types/api";

const PREVIEWABLE_MIME_TYPES = new Set([
  "text/plain",
  "text/csv",
  "application/json",
  "application/x-jsonlines",
]);

const MAX_PREVIEW_CHARS = 5000;

interface BlobRowProps {
  blob: BlobMetadata;
  sessionId: string;
  onDownload: (blobId: string) => void;
  onDelete: (blobId: string) => void;
  onUseAsInput: (blob: BlobMetadata) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function creatorBadge(createdBy: string): string {
  switch (createdBy) {
    case "user":
      return "\u{1F4E4}";
    case "assistant":
      return "\u{1F916}";
    case "pipeline":
      return "\u{2699}\u{FE0F}";
    default:
      return "";
  }
}

function statusIndicator(status: string): { color: string; label: string } {
  switch (status) {
    case "ready":
      return { color: "var(--color-success)", label: "Ready" };
    case "pending":
      return { color: "var(--color-warning)", label: "Pending" };
    case "error":
      return { color: "var(--color-error)", label: "Error" };
    default:
      return { color: "var(--color-text-muted)", label: status };
  }
}

export function BlobRow({ blob, sessionId, onDownload, onDelete, onUseAsInput }: BlobRowProps) {
  const status = statusIndicator(blob.status);
  const canPreview = PREVIEWABLE_MIME_TYPES.has(blob.mime_type);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const handleTogglePreview = async () => {
    if (previewOpen) {
      setPreviewOpen(false);
      return;
    }

    setPreviewOpen(true);

    // Only fetch if we haven't cached the content yet
    if (previewContent !== null) return;

    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const text = await previewBlobContent(sessionId, blob.id);
      setPreviewContent(text);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load preview";
      setPreviewError(message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const truncated = previewContent !== null && previewContent.length > MAX_PREVIEW_CHARS;
  const displayContent = truncated
    ? previewContent.slice(0, MAX_PREVIEW_CHARS)
    : previewContent;

  return (
    <div>
      <div
        className="blob-row"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 8px",
          borderBottom: previewOpen ? "none" : "1px solid var(--color-border)",
          fontSize: 13,
        }}
      >
        {/* Status dot */}
        <span
          title={status.label}
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            backgroundColor: status.color,
            flexShrink: 0,
          }}
        />

        {/* Creator badge */}
        <span title={`Created by ${blob.created_by}`} style={{ flexShrink: 0 }}>
          {creatorBadge(blob.created_by)}
        </span>

        {/* Filename */}
        <span
          style={{
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={blob.filename}
        >
          {blob.filename}
        </span>

        {/* Size */}
        <span
          style={{
            color: "var(--color-text-muted)",
            fontSize: 12,
            flexShrink: 0,
          }}
        >
          {formatBytes(blob.size_bytes)}
        </span>

        {/* Actions */}
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {canPreview && blob.status === "ready" && (
            <button
              onClick={handleTogglePreview}
              title={previewOpen ? "Hide preview" : "Preview content"}
              aria-label={`${previewOpen ? "Hide" : "Preview"} ${blob.filename}`}
              aria-expanded={previewOpen}
              className="blob-action-btn"
            >
              {"\uD83D\uDC41"}
            </button>
          )}
          {blob.status === "ready" && (
            <>
              <button
                onClick={() => onUseAsInput(blob)}
                title="Use as pipeline input"
                aria-label={`Use ${blob.filename} as input`}
                className="blob-action-btn"
              >
                {"\u25B6"}
              </button>
              <button
                onClick={() => onDownload(blob.id)}
                title="Download"
                aria-label={`Download ${blob.filename}`}
                className="blob-action-btn"
              >
                {"\u2B07"}
              </button>
            </>
          )}
          <button
            onClick={() => onDelete(blob.id)}
            title="Delete"
            aria-label={`Delete ${blob.filename}`}
            className="blob-action-btn"
          >
            {"\u2715"}
          </button>
        </div>
      </div>

      {/* Preview panel */}
      {previewOpen && (
        <div
          style={{
            padding: "8px 12px",
            borderBottom: "1px solid var(--color-border)",
            backgroundColor: "var(--color-surface-elevated)",
          }}
        >
          {previewLoading && (
            <div style={{ color: "var(--color-text-muted)", fontSize: 12 }}>
              Loading preview...
            </div>
          )}
          {previewError && (
            <div style={{ color: "var(--color-error)", fontSize: 12 }}>
              {previewError}
            </div>
          )}
          {displayContent !== null && !previewLoading && (
            <pre
              style={{
                margin: 0,
                padding: 8,
                fontFamily: "monospace",
                fontSize: 12,
                lineHeight: 1.4,
                maxHeight: 200,
                overflowY: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 4,
                color: "var(--color-text)",
              }}
            >
              {displayContent}
              {truncated && (
                <span style={{ color: "var(--color-text-muted)", fontStyle: "italic" }}>
                  {"\n... (truncated)"}
                </span>
              )}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
