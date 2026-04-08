// src/components/blobs/BlobManager.tsx
import { useEffect, useRef, useCallback, useMemo } from "react";
import { useBlobStore } from "@/stores/blobStore";
import { useSessionStore } from "@/stores/sessionStore";
import { BlobRow } from "./BlobRow";
import type { BlobMetadata, BlobCategory } from "@/types/api";

interface BlobManagerProps {
  onUseAsInput: (blob: BlobMetadata) => void;
}

/**
 * Categorize a blob into source/sink/other based on who created it.
 * - User uploads → source files (pipeline inputs)
 * - Pipeline outputs → sink files (results)
 * - Assistant-created → other (prompts, templates, config)
 */
function categorizeBlob(blob: BlobMetadata): BlobCategory {
  if (blob.created_by === "user") return "source";
  if (blob.created_by === "pipeline") return "sink";
  return "other";
}

const CATEGORY_LABELS: Record<BlobCategory, string> = {
  source: "Source files",
  sink: "Output files",
  other: "Other files",
};

const CATEGORY_ORDER: BlobCategory[] = ["source", "sink", "other"];

/**
 * Collapsible blob manager panel with categorized folders.
 * Shows session-scoped files grouped by source/output/other
 * with upload, download, delete, and "use as input" actions.
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

  const grouped = useMemo(() => {
    const groups: Record<BlobCategory, BlobMetadata[]> = {
      source: [],
      sink: [],
      other: [],
    };
    for (const blob of blobs) {
      groups[categorizeBlob(blob)].push(blob);
    }
    return groups;
  }, [blobs]);

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
        maxHeight: 280,
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

      {/* Categorized file list */}
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
          CATEGORY_ORDER.map((category) => {
            const categoryBlobs = grouped[category];
            if (categoryBlobs.length === 0) return null;
            return (
              <div key={category}>
                <div
                  style={{
                    padding: "4px 12px",
                    fontSize: 11,
                    fontWeight: 600,
                    color: "var(--color-text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    backgroundColor: "var(--color-surface-elevated)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {CATEGORY_LABELS[category]}
                </div>
                {categoryBlobs.map((blob) => (
                  <BlobRow
                    key={blob.id}
                    blob={blob}
                    onDownload={handleDownload}
                    onDelete={handleDelete}
                    onUseAsInput={onUseAsInput}
                  />
                ))}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
