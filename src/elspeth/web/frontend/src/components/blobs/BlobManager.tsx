// src/components/blobs/BlobManager.tsx
import { useEffect, useRef, useCallback } from "react";
import { useBlobStore } from "@/stores/blobStore";
import { useSessionStore } from "@/stores/sessionStore";
import { BlobRow } from "./BlobRow";
import type { BlobMetadata } from "@/types/api";

interface BlobManagerProps {
  onUseAsInput: (blob: BlobMetadata) => void;
}

/**
 * Collapsible blob manager panel. Shows session-scoped files with
 * upload, download, delete, and "use as input" actions.
 */
export function BlobManager({ onUseAsInput }: BlobManagerProps) {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const { blobs, isLoading, error, loadBlobs, uploadBlob, deleteBlob, downloadBlob } =
    useBlobStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (activeSessionId) {
      loadBlobs(activeSessionId);
    }
  }, [activeSessionId, loadBlobs]);

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file || !activeSessionId) return;
      try {
        await uploadBlob(activeSessionId, file);
      } catch {
        // Error is already in the store
      } finally {
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    },
    [activeSessionId, uploadBlob],
  );

  const handleDelete = useCallback(
    (blobId: string) => {
      if (!activeSessionId) return;
      deleteBlob(activeSessionId, blobId);
    },
    [activeSessionId, deleteBlob],
  );

  const handleDownload = useCallback(
    (blobId: string) => {
      if (!activeSessionId) return;
      downloadBlob(activeSessionId, blobId);
    },
    [activeSessionId, downloadBlob],
  );

  if (!activeSessionId) return null;

  return (
    <div
      className="blob-manager"
      style={{
        borderTop: "1px solid var(--color-border)",
        maxHeight: 200,
        display: "flex",
        flexDirection: "column",
        fontSize: 13,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 12px",
          borderBottom: "1px solid var(--color-border)",
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 12, color: "var(--color-text-secondary)" }}>
          Files ({blobs.length})
        </span>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="btn"
          style={{
            fontSize: 12,
            padding: "2px 8px",
            cursor: "pointer",
            minHeight: 36,
            minWidth: 44,
          }}
          aria-label="Upload file"
        >
          + Upload
        </button>
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleUpload}
          style={{ display: "none" }}
          aria-hidden="true"
          tabIndex={-1}
        />
      </div>

      {/* Error */}
      {error && (
        <div
          role="alert"
          style={{
            padding: "4px 12px",
            fontSize: 12,
            color: "var(--color-error)",
            backgroundColor: "var(--color-error-bg)",
          }}
        >
          {error}
        </div>
      )}

      {/* Blob list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          <div style={{ padding: 12, color: "var(--color-text-muted)", textAlign: "center" }}>
            Loading...
          </div>
        ) : blobs.length === 0 ? (
          <div style={{ padding: 12, color: "var(--color-text-muted)", textAlign: "center" }}>
            No files yet. Upload a file to get started.
          </div>
        ) : (
          blobs.map((blob) => (
            <BlobRow
              key={blob.id}
              blob={blob}
              onDownload={handleDownload}
              onDelete={handleDelete}
              onUseAsInput={onUseAsInput}
            />
          ))
        )}
      </div>
    </div>
  );
}
