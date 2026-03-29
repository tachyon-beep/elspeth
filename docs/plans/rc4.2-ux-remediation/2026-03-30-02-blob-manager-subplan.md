# RC4.2 UX Remediation — Blob Manager Implementation Plan

Date: 2026-03-30
Status: Draft
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## 1. Scope

This plan covers the new blob/file-management subsystem that replaces the
current raw upload-path workflow.

Included requirement:

- `REQ-API-01` — blob manager

Primary surfaces:

- session-scoped blob persistence and filesystem storage
- authenticated REST API
- assistant/composer blob tools
- execution-time blob lifecycle updates
- frontend blob manager UX and upload migration

This plan does not cover secrets or session forking beyond the explicit blob
inheritance contract needed to keep later work unblocked.

---

## 2. Current State

The current web UX has a narrow upload flow, not a blob subsystem:

- `POST /api/sessions/{id}/upload` writes a file under
  `{data_dir}/uploads/{user_id}/{filename}`
- the response returns a relative filesystem path
- `ChatInput.tsx` inserts that path into the chat text as
  `"I've uploaded a file at ..."`
- composer `set_source` path validation allows only
  `{data_dir}/uploads/`
- execution validation and execution runtime duplicate that same uploads-only
  allowlist check

This means the current product model is:

1. upload a file
2. receive a path string
3. paste or reference that path in chat
4. rely on the assistant to wire it into pipeline config

That is exactly the operational glue the blob manager is intended to remove.

---

## 3. Goals

- Let users upload, paste, browse, download, and reuse data without handling
  raw filesystem paths.
- Represent user-provided and run-produced files as first-class blob records.
- Map blobs cleanly to chat input, pipeline source input, run output, and
  downloadable artifacts.
- Preserve the boundary between user-facing blob objects and audit-facing
  payload capture.
- Keep all blob access session-owned and IDOR-safe.

Non-goals for this phase:

- cross-session shared blob libraries
- org/global blob catalogs
- rich inline content editing inside the blob manager
- full preview execution

---

## 4. Architecture Decisions

### AD-1: Blobs are session-scoped

The current web ownership model is session-centric, and the remediation work
already assumes session-oriented UX. The blob model should follow that shape.

Implications:

- each blob belongs to exactly one session
- blob routes stay under `/api/sessions/{id}/blobs`
- ownership checks reuse the existing session IDOR boundary
- forks can define explicit blob inheritance semantics later

This avoids inventing a new cross-session security model in the middle of RC4.2.

### AD-2: Blob IDs replace user-facing paths

The browser and assistant should interact with blob identifiers and blob
metadata, not raw storage paths.

Implications:

- upload/create responses return blob records, not `{path: ...}`
- chat UX references a blob by name/availability, not by filesystem path
- `set_source_from_blob` resolves storage paths server-side
- `set_output_to_blob` allocates a target blob server-side

Filesystem paths remain an internal implementation detail.

### AD-3: Blob storage is distinct from the legacy uploads scratch area

Blob storage should move to a dedicated namespace:

- `{data_dir}/blobs/{session_id}/{blob_id}_{filename}`

This separates managed blob lifecycle from the transitional uploads flow and
makes cleanup rules clearer.

The legacy `/upload` endpoint should be treated as a migration surface, not the
long-term product model.

### AD-4: PayloadStore remains the audit system; blobs remain the UX system

Blobs are not a replacement for Landscape/PayloadStore.

Rules:

- blob metadata tracks user-visible lifecycle and downloadability
- execution continues to record payload hashes and audit artifacts through the
  existing engine/runtime path
- when a blob is used as pipeline input or output, its `content_hash` should be
  compatible with the corresponding payload hash when the underlying bytes are
  identical

### AD-5: Output blobs use placeholder records updated after execution

For run-produced files, the sink target must exist before execution begins.

Pattern:

1. `set_output_to_blob` creates or reserves a blob record with
   `status: "pending"`
2. the sink writes to the reserved storage path
3. execution completion updates the blob to `ready` or `error`
4. metadata such as size and content hash is filled in post-write

### AD-6: Schema inference is explicit, not implicit on every upload

Blob creation should remain cheap and predictable. Schema inference can be
requested separately when needed.

This keeps upload latency down and avoids forcing content sniffing for binary
or large files.

### AD-7: Fork compatibility uses copy-on-fork

This plan assumes the later fork implementation will copy blob records and
backing files into the new session rather than sharing ownership across
sessions.

This keeps deletion, audit, and session archive semantics straightforward.

---

## 5. Proposed Blob Model

### Blob record shape

Minimum fields:

- `id`
- `session_id`
- `filename`
- `mime_type`
- `size_bytes`
- `content_hash`
- `storage_path` (internal only)
- `created_at`
- `created_by` (`user`, `assistant`, `pipeline`)
- `source_description`
- `schema_info`
- `status` (`ready`, `pending`, `error`)
- `input_to_run_ids`
- `output_from_run_id`

Notes:

- `storage_path` is never returned to the browser
- `schema_info` is nullable and populated only after explicit inference
- `input_to_run_ids` is UX/reporting metadata, not an authorization primitive

### Filesystem layout

Managed storage path:

- `{data_dir}/blobs/{session_id}/{blob_id}_{sanitized_filename}`

Rules:

- filename is sanitized using the same traversal-safe basename rule as the
  current upload path
- the blob ID prefixes the stored filename to avoid collisions
- storage directories are created lazily per session

---

## 6. API Surface

### REST endpoints

Recommended initial endpoints:

- `POST /api/sessions/{session_id}/blobs`
  - create blob from multipart upload
  - or create inline text/json payload via JSON body if we want one endpoint
- `GET /api/sessions/{session_id}/blobs`
  - list blob metadata
- `GET /api/sessions/{session_id}/blobs/{blob_id}`
  - fetch metadata
- `GET /api/sessions/{session_id}/blobs/{blob_id}/content`
  - download content
- `DELETE /api/sessions/{session_id}/blobs/{blob_id}`
  - delete metadata + backing file
- `POST /api/sessions/{session_id}/blobs/{blob_id}/infer-schema`
  - infer schema for CSV/JSON/JSONL/text-backed structured formats

### Composer tools

Recommended initial tools:

- `create_blob`
- `list_blobs`
- `get_blob_metadata`
- `delete_blob`
- `read_blob_text`
- `infer_blob_schema`
- `set_source_from_blob`
- `set_output_to_blob`

Assistant-oriented rules:

- discovery tools return blob IDs and user-safe metadata only
- mutation tools resolve paths internally
- the assistant never receives the internal storage path

---

## 7. Backend Design

### 7.1 Persistence

Add a new `blobs` table to the session database, alongside sessions, messages,
states, and runs.

Why the session DB:

- blobs are user-facing lifecycle objects
- ownership naturally follows session ownership
- run linkage already lives in the same database family
- this avoids mixing UX metadata into Landscape audit storage

### 7.2 Protocol and service layer

Add blob record/protocol types in the sessions-adjacent web layer, rather than
smuggling blob logic into route handlers.

Recommended components:

- `BlobRecord`
- `BlobCreateData`
- `BlobServiceProtocol`
- `BlobServiceImpl`

Core service operations:

- create uploaded blob
- create inline blob
- list session blobs
- get blob metadata
- delete blob
- read blob content
- infer blob schema
- reserve output blob
- mark blob ready/error after execution
- link blob to run usage

### 7.3 Route integration

Create a dedicated `web/blobs/` package instead of continuing to grow
`sessions/routes.py`.

Recommended layout:

- `src/elspeth/web/blobs/routes.py`
- `src/elspeth/web/blobs/protocol.py`
- `src/elspeth/web/blobs/service.py`
- `src/elspeth/web/blobs/schemas.py`

The session router can keep the legacy `/upload` endpoint temporarily, but it
should be documented as deprecated once blob creation is available.

### 7.4 Security and ownership

Every blob route must verify both:

1. the session belongs to the authenticated user
2. the blob belongs to that session

Use 404, not 403, for ownership failures to preserve the current anti-IDOR
pattern.

Do not trust blob IDs alone without the session boundary.

### 7.5 Path policy migration

There are currently three separate places that assume source files live under
`{data_dir}/uploads/`:

- composer tool path validation
- execution validation
- execution runtime guard in `ExecutionServiceImpl.execute()`

The blob rollout needs a coordinated migration:

1. keep raw-path validation for legacy upload compatibility
2. add blob-native source wiring that bypasses user-provided filesystem paths
3. update validation/runtime checks so blob-backed sources are validated by
   blob ownership/resolution, not by a direct `uploads/` path comparison

The preferred end state is:

- user-facing tools use blob references
- direct path-based source wiring becomes legacy/escape hatch behavior

### 7.6 Execution integration

The execution service needs a post-run blob lifecycle hook for output blobs.

Required behaviors:

- when a run starts, pending output blobs remain pending
- when a run completes successfully, ready output blobs get:
  - final `size_bytes`
  - `content_hash`
  - `status: "ready"`
  - `output_from_run_id`
- when a run fails before writing the output:
  - blob is marked `error`
  - partial file cleanup policy is explicit

For input blobs used by a run, execution should also record linkage so the UX
can say which runs consumed a given blob.

### 7.7 Schema inference

Supported initial formats:

- CSV
- JSON array
- JSONL

Optional low-effort support:

- plain text returns a trivial text/blob description rather than tabular schema

Inference should inspect only a bounded prefix of rows or bytes and return:

- detected format
- field names
- inferred primitive types
- nullability/required guess
- sample values
- inference warnings

---

## 8. Frontend Design

### 8.1 Blob manager surface

Add a dedicated blob manager UI in the web app.

Initial capabilities:

- list blobs for the active session
- upload a file
- create a text blob from pasted content
- download a blob
- delete a blob
- invoke “use as input”
- show run linkage and status

This can live in a drawer/panel rather than a full-page view.

### 8.2 Chat upload migration

`ChatInput.tsx` should stop appending raw storage paths into the chat textbox.

New behavior:

- upload creates a blob
- composer text area can optionally receive a human-facing helper string like
  `"I uploaded 'rules.json'; please use it as the pipeline input."`
- better yet, the UI can show an attached blob chip outside the raw text

For this phase, a helper sentence is acceptable if it references the blob by
filename and/or blob ID, not by storage path.

### 8.3 Drag-and-drop

The drag-and-drop interaction should be treated as a blob creation affordance,
not a separate upload mechanism.

Same backend path, same resulting metadata, same session ownership model.

### 8.4 Use-as-input flow

The blob manager needs a concrete “use as input” action.

Recommended first pass:

- selecting “use as input” does not directly mutate the pipeline
- instead, it inserts a clear assistant-facing prompt into chat referencing the
  selected blob

Stronger later pass:

- if the assistant/composer has the necessary blob tools, the chat or tool flow
  can call `set_source_from_blob` directly

This keeps the first version useful without requiring fully autonomous source
wiring on day one.

---

## 9. Implementation Phases

### Phase 1: Data model and service foundation

- add `blobs` table
- add blob record/protocol types
- implement blob service with filesystem-backed storage
- implement filename sanitization and delete semantics

Deliverable:

- backend can create, list, fetch, and delete session-scoped blobs safely

### Phase 2: REST API

- add blob router and schemas
- wire router into app startup
- implement ownership-safe CRUD endpoints
- implement content download endpoint

Deliverable:

- frontend and future assistant tools can interact with blob resources via REST

### Phase 3: Frontend blob manager

- add blob list UI for active session
- migrate file upload to blob creation
- add download/delete actions
- add create-text-blob affordance if feasible in this pass

Deliverable:

- the user can manage inputs without seeing a filesystem path

### Phase 4: Composer tool integration

- add blob discovery/mutation tools
- add `set_source_from_blob`
- add `set_output_to_blob`
- ensure tool responses remain user-safe and path-free

Deliverable:

- the assistant can reason over blobs as first-class pipeline inputs/outputs

### Phase 5: Execution lifecycle integration

- reserve output blobs before execution
- update output blobs after run completion/failure
- link input/output blobs to runs
- align blob lifecycle with execution validation/runtime checks

Deliverable:

- output files participate in the same blob UX as uploaded inputs

### Phase 6: Schema inference and polish

- implement explicit inference endpoint/tool
- surface schema summaries in blob manager
- add UX polish around “use as input”

Deliverable:

- structured files become easier to inspect and wire correctly

---

## 10. File-Level Work

### Backend

Expected new files:

- `src/elspeth/web/blobs/routes.py`
- `src/elspeth/web/blobs/protocol.py`
- `src/elspeth/web/blobs/service.py`
- `src/elspeth/web/blobs/schemas.py`

Expected modified files:

- `src/elspeth/web/app.py`
- `src/elspeth/web/sessions/models.py`
- `src/elspeth/web/sessions/protocol.py` or adjacent protocol surface if blob
  records are kept nearby
- `src/elspeth/web/sessions/routes.py`
- `src/elspeth/web/composer/tools.py`
- `src/elspeth/web/execution/service.py`
- `src/elspeth/web/execution/validation.py`

### Frontend

Expected new files:

- `src/elspeth/web/frontend/src/components/blobs/BlobManager.tsx`
- `src/elspeth/web/frontend/src/components/blobs/BlobRow.tsx`
- `src/elspeth/web/frontend/src/stores/blobStore.ts` or equivalent API/store
  integration

Expected modified files:

- `src/elspeth/web/frontend/src/api/client.ts`
- `src/elspeth/web/frontend/src/types/index.ts`
- `src/elspeth/web/frontend/src/components/chat/ChatInput.tsx`
- layout/container component that hosts the blob manager drawer

---

## 11. Testing Plan

### Backend tests

- blob create/list/get/delete happy path
- ownership failures return 404
- filename traversal attempts are rejected/sanitized safely
- large-upload limits still enforced
- output blob reservation and completion updates
- blob-backed source wiring resolves only to owned session blobs

### Frontend tests

- upload creates blob and updates blob list
- upload no longer inserts raw filesystem paths into chat
- delete/download actions work against active session blobs
- “use as input” action produces the intended UX affordance

### Manual checks

1. Upload a file and confirm it appears in blob manager with safe metadata.
2. Use that blob as pipeline input without ever seeing a storage path.
3. Run a pipeline that writes to an output blob and confirm the blob becomes
   downloadable after completion.
4. Try cross-session blob access and confirm it fails with 404 semantics.

---

## 12. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Blob scope creeps toward a cross-session file system | High | Keep ownership strictly session-scoped for RC4.2 |
| Path-allowlist migration leaves inconsistent behavior | High | Update composer, validation, and execution guards as one coordinated change |
| Output blobs require sink integration details not yet exposed | Medium | Phase output reservation after basic CRUD/UI work |
| Blob manager UI grows into a full document browser | Medium | Keep the initial scope to lifecycle actions and input/output mapping |
| Schema inference adds latency or brittle parsing | Low | Make inference explicit and bounded, not automatic |

---

## 13. Sequencing

Recommended order inside this subplan:

1. Data model and blob service
2. REST API
3. Frontend upload/blob manager migration
4. Composer blob tools
5. Execution lifecycle integration
6. Schema inference and UX polish

That order gets the highest-value UX change first: users stop handling raw file
paths even before the assistant has the full blob-aware tool surface.
