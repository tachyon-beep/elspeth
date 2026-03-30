// src/components/blobs/BlobRow.tsx
import type { BlobMetadata } from "@/types/api";

interface BlobRowProps {
  blob: BlobMetadata;
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

export function BlobRow({ blob, onDownload, onDelete, onUseAsInput }: BlobRowProps) {
  const status = statusIndicator(blob.status);

  return (
    <div
      className="blob-row"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 8px",
        borderBottom: "1px solid var(--color-border)",
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
  );
}
