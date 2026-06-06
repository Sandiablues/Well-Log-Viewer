# Loader Workflow Contract v1

## Governance Alignment

This contract is subordinate to and governed by the Seismic Viewer application-development governance documents:

- `docs/governance/AI_DEVELOPMENT_RULES.md`
- `docs/governance/SEISMIC_VIEWER_CONTROL_PACK.md`
- `docs/governance/AGENT_TASK_PROTOCOL.md`
- `docs/governance/BLOCK_RESULT_TEMPLATE.md`
- `docs/governance/STRUCTURAL_FIX_REPORT_TEMPLATE.md`

Any code block implementing this contract must follow the control-pack process:

- architecture preflight before coding
- explicit allowed and forbidden files
- one bounded implementation attempt
- no brittle regex/string/JSX micro-patching
- backend-owned lifecycle and data contracts
- frontend renders backend-owned state
- stop and produce a structural-fix report if ownership or contract boundaries are unclear

---

## Purpose

This document defines the target architecture for the MultiViewer loader workflow.

The current data workflow has three user-facing management areas:

- Source Repository
- External Data Registry
- Managed Data

This split has created duplicated state, unclear ownership, stale selections, source-record versus MSI-record confusion, and fragile delete/rebuild behavior.

The target model is:

- Source Intake
- Managed Data

Source Intake consolidates Source Repository, External Data Registry, load sheet review, candidate classification, and conversion request preparation.

Managed Data remains separate and is owned by MSI-backed managed representations.

This contract is the governing reference for rebuilding the loader workflow. Code changes should conform to this document unless a later approved contract replaces it.

---

## Core Decision

Source Repository and External Data Registry should be consolidated into one user-facing workflow called Source Intake.

Managed Data should remain separate.

Source Intake owns raw and pre-managed source lifecycle.

Managed Data owns converted, indexed, viewer-ready, or managed representations.

---

## Target User-Facing Structure

### Data

- Source Intake
- Managed Data
- Viewer

### Source Intake

Source Intake includes:

- Source repositories
- Scan results
- Discovered SEG-Y files
- Supporting documents
- Candidate classification
- Load sheet / review sheet
- Build requests
- Conversion jobs

### Managed Data

Managed Data includes:

- Managed 2D line representations
- Managed 3D volume representations
- Indexed previews
- Converted Zarr or future OpenVDS representations
- Loaded / unloaded state
- Metadata status
- Document attachments
- Viewer actions
- Delete / archive / rebuild actions

---

## Responsibility Split

### Source Intake

Source Intake is responsible for everything before a managed representation exists.

It owns:

- Repository registration
- Repository scanning
- Folder structure interpretation
- Source file discovery
- Supporting document discovery
- Candidate classification
- Load sheet review
- Metadata hints
- Evidence hints
- Candidate approval
- Build request creation
- Conversion job monitoring

Source Intake must not be the authority for viewer-ready managed data.

### Managed Data

Managed Data is responsible for everything after a managed representation exists.

It owns:

- Listing MSI-backed representations
- Loading into viewer selection
- Unloading from viewer selection
- Soft-delete from Managed Data
- Metadata summary display
- Document association display
- Managed representation info
- Rebuild request entry points
- QAQC state display

Managed Data must not discover source files or infer source candidate classification.

---

## Backend Service Boundaries

### SourceIntakeService

Owns source-side workflow.

Responsibilities:

- Create and update source repositories
- Scan repositories
- Build discovered source candidate records
- Classify source candidates
- Maintain load sheet / review state
- Track source candidate state
- Expose source intake rows to frontend

### ManagedRepresentationRequestService

Owns the transition from source candidate to managed representation request.

Responsibilities:

- Accept build 2D line request
- Accept build 3D volume request
- Accept build SEG-Y index request
- Validate candidate compatibility with requested representation
- Create conversion job with explicit target contract
- Select storage target via StorageService
- Submit work to ConversionJobService

This service is the missing boundary between Source Intake and conversion.

### ConversionJobService

Owns execution of conversion jobs.

Responsibilities:

- Run explicit conversion jobs
- Honor requested target type
- Call low-level seismic conversion operations
- Validate post-conversion output contract
- Return conversion result metadata

ConversionJobService must never silently change target type.

If a request is for a 2D line, it must produce 2D output or fail.

If a request is for a 3D volume, it must produce 3D output or fail.

### SeismicService

Owns low-level seismic file operations only.

Responsibilities:

- Read SEG-Y metadata
- Read trace and sample data
- Convert SEG-Y to Zarr
- Produce 2D trace/sample arrays
- Produce 3D inline/crossline/sample arrays when valid
- Return technical metadata

SeismicService must not own product lifecycle state.

### StorageService

Owns physical and logical storage.

Responsibilities:

- Allocate storage target paths
- Resolve logical URIs to physical paths
- Enforce EndRepo path conventions
- Validate storage existence
- Preserve future object-storage abstraction

StorageService owns the mapping between:

- endrepo://...
- /endrepo/...
- local filesystem paths

### MSIRegistrationService

Owns registration of validated managed representations.

Responsibilities:

- Register MSI dataset records
- Register MSI representation records
- Validate storage and metadata contract
- Reject mismatched contracts
- Mark representation viewer_ready only when valid

### ManagedDataService

Owns frontend-facing Managed Data behavior.

Responsibilities:

- List managed rows
- List loaded rows
- Load representation
- Unload representation
- Soft-delete representation
- Expose row actions
- Expose row status

ManagedDataService may wrap MSI routes initially, but the frontend should consume ManagedDataService-style contracts.

---

## Canonical Workflow

The target workflow is:

1. Add Source Repository
2. Scan repository
3. Discover files and documents
4. Classify candidates
5. Review / edit load sheet fields
6. Approve candidate
7. Request managed representation build
8. Create conversion job
9. Convert using explicit target contract
10. Write artifact to StorageService target
11. Validate output contract
12. Register MSI dataset and representation
13. Display representation in Managed Data
14. Load into viewer when explicitly requested

A file must not appear in Managed Data until MSI has a valid managed representation.

---

## Source Candidate State Model

Allowed source candidate states:

- discovered
- classified
- review_required
- approved
- submitted
- build_requested
- building
- managed_available
- failed
- excluded

Source candidate state is separate from managed representation state.

---

## Managed Representation State Model

Allowed managed representation states:

- not_created
- queued
- building
- metadata_ready
- viewer_ready
- failed
- stale
- deleted
- superseded

Managed Data should normally show viewer_ready representations.

For testing, Managed Data may also show diagnostic states if explicitly enabled, but normal MD should not show deleted, failed, or missing rows.

---

## Conversion Job State Model

Allowed conversion job states:

- queued
- running
- completed
- failed
- cancelled

Job state is separate from source candidate state and managed representation state.

---

## Storage State Model

Allowed storage states:

- not_written
- writing
- available
- missing
- quarantined
- deleted

Storage state is separate from MSI lifecycle state.

---

## 2D Managed Line Contract

A 2D managed line request must produce:

- target_type = 2d_line
- dataset_type = 2d_line
- representation_type = zarr_2d
- viewer_mode = 2d
- metadata.is_3d = false
- axis_order = ["trace", "sample"]
- storage path under managed/zarr/2d
- storage_uri under endrepo://managed/zarr/2d or approved legacy equivalent
- zarr_url under /endrepo/managed/zarr/2d or approved legacy equivalent

A 2D workflow must not silently produce inline/crossline/sample output.

If trace headers look grid-like but the request is explicitly 2D, the converter must either:

- produce trace/sample 2D output, or
- fail with review_required

It must not create a pseudo-3D cube.

---

## 3D Managed Volume Contract

A 3D managed volume request must produce:

- target_type = 3d_volume
- dataset_type = 3d_volume
- representation_type = zarr_3d
- viewer_mode = 3d
- metadata.is_3d = true
- axis_order = ["inline", "crossline", "sample"]
- storage path under managed/zarr/3d
- storage_uri under endrepo://managed/zarr/3d or approved legacy equivalent
- zarr_url under /endrepo/managed/zarr/3d or approved legacy equivalent

If a 3D request cannot establish valid inline/crossline/sample geometry, it must fail with review_required.

It must not register as viewer_ready.

---

## MSI Registration Contract

MSI registration must reject any representation where the contract is internally inconsistent.

Reject if:

- 2D representation points to managed/zarr/3d
- 3D representation points to managed/zarr/2d
- zarr_url and storage_uri disagree on dimensional folder
- zarr_2d has metadata.is_3d = true
- zarr_3d has metadata.is_3d = false
- storage target does not exist
- required metadata is missing
- target type differs from representation type

Only valid representations may become viewer_ready.

---

## Managed Data Row Contract

A Managed Data row must be backend-owned and must include:

- representation_id
- physical_artifact_id
- display_name
- dataset_type
- representation_type
- viewer_mode
- lifecycle_state
- storage_uri
- zarr_url
- is_loaded
- can_load
- can_unload
- can_delete
- can_rebuild
- metadata_status
- document_status
- available actions

Frontend must render these values.

Frontend must not infer lifecycle truth from filename, zarr path, source record, or stale local state.

---

## Delete Contract

For the current testing phase:

Managed Data Delete means soft-delete the MSI representation.

Required behavior:

- lifecycle_state = deleted
- viewer_ready = false
- is_preferred = false
- loaded state cleared
- row disappears from normal Managed Data
- physical artifact remains unless explicit purge is requested

Delete must operate on MSI representation ID.

Delete must not require the original source SEG-Y record to exist.

Later, the product may add separate actions:

- Archive
- Quarantine
- Purge physical artifact
- Rebuild from source

These should not be overloaded into the basic Delete action.

---

## Rebuild Contract

Rebuild should be a source-side or managed-representation-side action, but the target must be explicit.

A rebuild request must specify:

- source_candidate_id or representation_id
- target_type
- target_representation_type
- storage policy
- overwrite or supersede behavior

Rebuild must not reuse stale inferred state from old failed representations.

---

## Source Intake API Target

Future preferred API surface:

- GET /api/source-intake/repositories
- POST /api/source-intake/repositories
- POST /api/source-intake/repositories/{id}/scan
- GET /api/source-intake/candidates
- GET /api/source-intake/candidates/{id}
- PATCH /api/source-intake/candidates/{id}
- POST /api/source-intake/candidates/{id}/approve
- POST /api/source-intake/candidates/{id}/build-2d-line
- POST /api/source-intake/candidates/{id}/build-3d-volume
- GET /api/source-intake/jobs

These endpoints may initially wrap existing services.

---

## Managed Data API Target

Future preferred API surface:

- GET /api/managed-data
- GET /api/managed-data/loaded
- POST /api/managed-data/{representation_id}/load
- POST /api/managed-data/{representation_id}/unload
- DELETE /api/managed-data/{representation_id}
- GET /api/managed-data/{representation_id}/info
- GET /api/managed-data/{representation_id}/metadata-summary
- GET /api/managed-data/{representation_id}/documents

These endpoints may initially wrap existing MSI services.

---

## Reuse Plan

Reuse the following components where possible:

- EndRepo folder structure
- StorageService
- MSIRepository
- MSIRegistrationService
- MSI viewer resolver
- MSI load/unload/delete behavior
- SeismicService low-level SEG-Y/Zarr operations
- Existing repository scan logic
- Existing load sheet logic
- Existing candidate classification fields
- Existing Managed Data panel layout where possible

Refactor or replace the orchestration around them.

---

## Migration Plan

### Phase 1 — Contract and façade

- Keep current internals
- Add Source Intake façade
- Add Managed Data façade
- Route frontend through façade endpoints

### Phase 2 — State model cleanup

- Replace scattered can_create/can_delete logic
- Make lifecycle state backend-owned and deterministic
- Align source candidate state and managed representation state

### Phase 3 — Managed representation request service

- Move build actions out of document API ownership
- Create explicit request contract
- Carry target type into job creation

### Phase 4 — Conversion hardening

- Enforce 2D/3D contracts
- Add contract tests
- Reject invalid registrations

### Phase 5 — UI consolidation

- Combine SR and EDR into Source Intake
- Keep Managed Data separate
- Hide old SR/EDR pages or retain as internal diagnostics only

---

## Explicit Non-Goals

Do not:

- Merge Managed Data into Source Intake
- Rewrite SeismicService from scratch
- Delete MSI and return to volumes.json as authority
- Keep source-record-dependent Managed Data actions
- Let frontend infer lifecycle truth
- Continue patching large JSX files casually
- Use documents.py as the long-term conversion action owner
- Allow 2D requests to become 3D outputs
- Allow invalid storage/MSI combinations to become viewer_ready

---

## Current Testing Rule

During this rebuild, test with one small dataset at a time.

Do not run bulk conversion.

Do not load large volumes until Source Intake and Managed Data contracts are stable.

---

## Governing Rule

The loader workflow must be rebuilt around explicit backend-owned contracts.

Frontend renders state and invokes actions.

Backend owns lifecycle truth.
