// ============================================================================
// ELSPETH Frontend Type Definitions
//
// Hand-written types mirroring backend Pydantic schemas. These are the
// contract between frontend and backend. When openapi-typescript generation
// is available, these can be replaced with imports from the generated file.
// ============================================================================

// ── Auth ────────────────────────────────────────────────────────────────────

/**
 * Auth provider configuration returned by GET /api/auth/config.
 * This endpoint is unauthenticated (callable before login).
 * The response is cached in memory for the session lifetime.
 */
export interface AuthConfig {
  provider: "local" | "oidc" | "entra";
  oidc_issuer: string | null;
  oidc_client_id: string | null;
}

/**
 * Minimal identity claims extracted from the JWT or session.
 * Used internally for attribution and display.
 */
export interface UserIdentity {
  user_id: string;
  username: string;
}

/**
 * Full user profile returned by GET /api/auth/me.
 * Extends UserIdentity with display-oriented fields.
 */
export interface UserProfile {
  user_id: string;
  username: string;
  display_name: string;
  email: string | null;
  groups: string[];
}

// ── Sessions ────────────────────────────────────────────────────────────────

/** Session summary for sidebar listing. */
export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  forked_from_session_id?: string;
  forked_from_message_id?: string;
}

// ── Messages ────────────────────────────────────────────────────────────────

/**
 * A single tool call within an assistant message.
 * Uses LiteLLM wire format as stored in the chat_messages.tool_calls column.
 * The `arguments` field is a JSON-encoded string, not a parsed object.
 */
export interface ToolCall {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string;
  };
}

/** A chat message in a session. */
export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tool_calls: ToolCall[] | null;
  created_at: string;
  local_status?: "pending" | "failed";
  composition_state_id?: string;
}

// ── Composition State ───────────────────────────────────────────────────────

/** Source specification within a pipeline composition. */
export interface SourceSpec {
  plugin: string;
  options: Record<string, unknown>;
}

/**
 * A node in the pipeline composition DAG.
 * Represents a source, transform, gate, or sink.
 */
export interface NodeSpec {
  id: string;
  name: string;
  type: "source" | "transform" | "gate" | "sink";
  plugin: string;
  config: Record<string, unknown>;
  config_summary: string;
}

/** An edge connecting two nodes in the DAG. */
export interface EdgeSpec {
  source: string;
  target: string;
  label: string | null;
  edge_type: "continue" | "route" | "error";
}

/** Output/sink specification within a pipeline composition. */
export interface OutputSpec {
  name: string;
  plugin: string;
  options: Record<string, unknown>;
}

/** Pipeline-level metadata attached to a composition. */
export interface PipelineMetadata {
  name: string | null;
  description: string | null;
}

/**
 * The full pipeline composition state.
 *
 * This is the central data structure that flows through the system:
 * - Created/updated by the composer tool-use loop
 * - Persisted via SessionService
 * - Validated by the validation pipeline
 * - Rendered by the frontend inspector panel
 * - Converted to YAML for execution
 */
export interface CompositionState {
  version: number;
  source: SourceSpec | null;
  nodes: NodeSpec[];
  edges: EdgeSpec[];
  outputs: OutputSpec[];
  metadata: PipelineMetadata;
  validation_errors?: string[];
}

/** A version history entry for CompositionState. */
export interface CompositionStateVersion {
  id: string;
  version: number;
  created_at: string;
  node_count: number;
}

// ── Plugin Catalog ──────────────────────────────────────────────────────────

/** Plugin summary from the catalog listing endpoints. */
export interface PluginSummary {
  name: string;
  type: "source" | "transform" | "gate" | "sink";
  description: string;
}

/** Detailed plugin schema info including configuration JSON Schema. */
export interface PluginSchemaInfo {
  name: string;
  type: "source" | "transform" | "gate" | "sink";
  description: string;
  config_schema: Record<string, unknown>;
}

// ── Validation ──────────────────────────────────────────────────────────────

/**
 * A single check performed during pipeline validation.
 * Represents one discrete validation step (schema compatibility,
 * route validity, source path security, etc.).
 */
export interface ValidationCheck {
  name: string;
  passed: boolean;
  detail: string;
}

/**
 * A single validation error with per-component attribution.
 * Stage 2 errors include component_id and optional suggestion,
 * unlike Stage 1 errors which are simple strings.
 */
export interface ValidationError {
  component_id: string;
  component_type: string;
  message: string;
  suggestion: string | null;
}

/**
 * Full validation result from POST /api/sessions/{id}/validate.
 * Stage 2 validation with per-component detail.
 */
export interface ValidationResult {
  is_valid: boolean;
  summary: string;
  checks: ValidationCheck[];
  errors: ValidationError[];
}

// ── Execution ───────────────────────────────────────────────────────────────

/** An execution run. */
export interface Run {
  id: string;
  session_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  rows_processed: number;
  rows_failed: number;
  started_at: string;
  finished_at: string | null;
  composition_version: number;
}

/**
 * A progress event from the WebSocket.
 *
 * The backend sends a nested envelope: top-level fields identify the event,
 * and `data` carries the type-specific payload.
 *
 * Terminal semantics:
 * - "progress" -- non-terminal. Row count update; pipeline still running.
 * - "error" -- non-terminal. Per-row exception; pipeline continues processing.
 *   The frontend appends the error to the exceptions list but does NOT stop
 *   the progress view or close the WebSocket.
 * - "completed" -- terminal. Pipeline finished successfully.
 * - "cancelled" -- terminal. Pipeline was cancelled.
 *
 * Note: "failed" is a Run status (set when the pipeline aborts), not a
 * RunEvent type. If the pipeline aborts, the WebSocket closes and the
 * frontend fetches the final Run status via REST.
 */
export interface RunEvent {
  run_id: string;
  timestamp: string;
  event_type: "progress" | "error" | "completed" | "cancelled";
  data: RunEventProgress | RunEventError | RunEventCompleted | RunEventCancelled;
}

export interface RunEventProgress {
  rows_processed: number;
  rows_failed: number;
}

export interface RunEventError {
  message: string;
  node_id: string | null;
  row_id: string | null;
}

export interface RunEventCompleted {
  rows_processed: number;
  rows_succeeded: number;
  rows_failed: number;
  rows_quarantined: number;
  landscape_run_id: string;
}

export interface RunEventCancelled {
  rows_processed: number;
  rows_failed: number;
}

/** Live progress state derived from RunEvents. */
export interface RunProgress {
  rows_processed: number;
  rows_failed: number;
  recent_errors: RunEventError[];
  status: "running" | "completed" | "cancelled";
}

// ── API Error Envelope ──────────────────────────────────────────────────────

/**
 * Typed API error response.
 *
 * All non-2xx responses across the entire API use this envelope:
 * - `detail`: Human-readable error message (always present)
 * - `error_type`: Machine-readable discriminator (present on domain errors,
 *   absent on generic HTTP errors)
 * - `validation_errors`: Per-component errors (present on validation failures)
 *
 * The frontend checks error_type first (if present), falls back to HTTP
 * status code, then falls back to detail text.
 */
export interface ApiError {
  status: number;
  detail: string;
  error_type?: string;
  validation_errors?: ValidationError[];
}

export interface SystemStatus {
  composer_available: boolean;
  composer_model: string;
  composer_provider: string | null;
  composer_reason: string | null;
  composer_missing_keys: string[];
}

// ── File Upload ─────────────────────────────────────────────────────────────

/** Response from POST /api/sessions/{id}/upload. */
export interface UploadResult {
  path: string;
  filename: string;
  size_bytes: number;
}

// ── Blob Manager ────────────────────────────────────────────────────────────

/** Blob metadata returned by all blob endpoints. */
export interface BlobMetadata {
  id: string;
  session_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  content_hash: string | null;
  created_at: string;
  created_by: "user" | "assistant" | "pipeline";
  source_description: string | null;
  status: "ready" | "pending" | "error";
}

// ── Secret References ───────────────────────────────────────────────────────

/** Secret inventory item — browser-safe metadata, never contains values. */
export interface SecretInventoryItem {
  name: string;
  scope: "user" | "server" | "org";
  available: boolean;
  source_kind: string;
}
