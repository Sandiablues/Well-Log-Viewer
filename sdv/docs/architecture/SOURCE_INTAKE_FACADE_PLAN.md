# Source Intake Façade Plan

## Governance Alignment

This plan is governed by:

- `docs/governance/AI_DEVELOPMENT_RULES.md`
- `docs/governance/SEISMIC_VIEWER_CONTROL_PACK.md`
- `docs/governance/AGENT_TASK_PROTOCOL.md`
- `docs/governance/BLOCK_RESULT_TEMPLATE.md`
- `docs/governance/STRUCTURAL_FIX_REPORT_TEMPLATE.md`
- `docs/architecture/LOADER_WORKFLOW_CONTRACT_V1.md`

This document defines the first implementation step toward consolidating Source Repository and External Data Registry into Source Intake.

This is an architecture and API façade plan. It is not a rewrite plan.

---

## Purpose

The current loader workflow exposes Source Repository and External Data Registry as separate user-facing concepts.

That split creates confusion because both areas manage different stages of the same source-side lifecycle:

- source folder registration
- scanning
- load sheet review
- candidate classification
- staging/submission
- conversion readiness

The goal of this façade is to introduce a single backend-facing Source Intake API while reusing existing internals.

---

## Core Decision

Create a Source Intake façade over the existing SR and EDR services.

Do not remove existing routes yet.

Do not rewrite scanning, load sheet, or candidate classification internals yet.

Do not change Managed Data in this block.

---

## Target API Surface

Initial façade endpoints:

- `GET /api/source-intake/repositories`
- `POST /api/source-intake/repositories`
- `GET /api/source-intake/repositories/{repository_id}`
- `POST /api/source-intake/repositories/{repository_id}/scan`
- `GET /api/source-intake/repositories/{repository_id}/load-sheet`
- `POST /api/source-intake/repositories/{repository_id}/stage`
- `POST /api/source-intake/repositories/{repository_id}/stage/submit`
- `GET /api/source-intake/candidates`
- `GET /api/source-intake/candidates/{candidate_id}`
- `GET /api/source-intake/repositories/{repository_id}/candidates`
- `GET /api/source-intake/jobs`

Later endpoints, not part of the first façade block:

- `POST /api/source-intake/candidates/{candidate_id}/approve`
- `POST /api/source-intake/candidates/{candidate_id}/build-2d-line`
- `POST /api/source-intake/candidates/{candidate_id}/build-3d-volume`
- `POST /api/source-intake/candidates/{candidate_id}/build-index`

---

## First Façade Block Scope

The first implementation block should create read/forwarding façade routes only.

Allowed behavior:

- wrap existing repository listing
- wrap existing repository detail
- wrap existing load sheet route
- wrap existing staging route
- wrap existing stage submit route
- wrap existing submitted-view / EDR rows as Source Intake candidates
- return a normalized candidate row shape where practical

Forbidden behavior:

- no conversion changes
- no storage changes
- no MSI registration changes
- no Managed Data frontend changes
- no deletion behavior changes
- no large `DataManager.tsx` surgery
- no removal of existing SR/EDR routes

---

## Reuse Targets

Reuse existing backend internals:

- repository API/service
- package registry service
- dataset registry service
- source SEG-Y classification fields
- load sheet logic
- staging and submit logic
- submitted-view / external registry result shaping

The façade should be a thin boundary over these until the service layer is rebuilt.

---

## Source Intake Repository Row Contract

A Source Intake repository row should expose:

- `repository_id`
- `name`
- `root_path`
- `source_structure_type`
- `intended_use`
- `created_at`
- `updated_at`
- `last_scan_at`
- `scan_status`
- `candidate_count`
- `review_required_count`
- `approved_count`
- `submitted_count`

If fields are not available yet, return `null` rather than inferring in the frontend.

---

## Source Intake Candidate Row Contract

A Source Intake candidate row should expose:

- `candidate_id`
- `repository_id`
- `package_id`
- `line_id`
- `source_segy_file_id`
- `filename`
- `relative_path`
- `source_path_exists`
- `candidate_kind`
- `candidate_role`
- `classification_source`
- `classification_confidence`
- `classification_reasons`
- `review_state`
- `conversion_state`
- `managed_state`
- `can_build_2d`
- `can_build_3d`
- `can_build_index`
- `status_label`
- `status_reason`

The backend owns these fields.

The frontend must not infer candidate kind or build eligibility from filename alone.

---

## Source Intake Load Sheet Contract

The load sheet remains source-side.

It should expose:

- `repository_id`
- `rows[]`
- `documents[]`
- `scan_summary`
- `classification_summary`
- `review_summary`

Each row should include:

- source item identity
- candidate classification
- editable metadata hints
- review state
- evidence hints
- available source-side actions

---

## Candidate Build Eligibility Rules

Initial rules should be backend-owned:

- `can_build_2d = candidate_kind == "2d_line" and source_path_exists and not already viewer_ready`
- `can_build_3d = candidate_kind == "3d_volume" and source_path_exists and not already viewer_ready`
- `can_build_index = source_path_exists and candidate_kind in ["2d_line", "3d_volume", "review_required"]`

These rules may later move into `ManagedRepresentationRequestService`.

For the first façade block, expose fields only if they are already reliable. Otherwise expose `null`.

---

## Relationship to Managed Data

Source Intake must not list MSI rows as Managed Data.

Managed Data remains MSI-backed.

Source Intake may show whether a source candidate has a managed representation, but it must not become the owner of that representation.

Example source-side status:

- `not_created`
- `building`
- `viewer_ready`
- `failed`
- `stale`
- `deleted`
- `unknown`

The source candidate may link to the MSI representation ID if known.

---

## Frontend Migration Strategy

Phase 1:

- Add backend façade only.
- Keep existing SR and EDR frontend panels unchanged.

Phase 2:

- Create Source Intake page shell.
- Embed existing SR and EDR components inside it.
- Use old endpoints if necessary.

Phase 3:

- Move SR/EDR panels to call `/api/source-intake/...`.
- Rename UI sections around Source Intake terminology.
- Hide old SR/EDR navigation once stable.

---

## Backend Migration Strategy

Phase 1:

- Add `app/api/source_intake.py`.
- Register router in `main.py`.
- Use existing services underneath.
- No internal service rewrite.

Phase 2:

- Add `SourceIntakeService`.
- Move façade route logic into service.
- Normalize candidate row model.

Phase 3:

- Add `ManagedRepresentationRequestService`.
- Move build actions out of source lifecycle / documents API coupling.

---

## Stop Conditions

Stop and produce a structural-fix report if:

- repository and EDR state cannot be joined without guessing
- source candidate identity is unstable
- façade requires frontend lifecycle inference
- façade requires rewriting conversion behavior
- route ownership is unclear
- implementation touches large JSX files unnecessarily
- endpoint behavior would create a second source of truth

---

## Required Validation For First Implementation Block

The first backend façade implementation should validate:

- `GET /api/source-intake/repositories` returns 200
- `GET /api/source-intake/candidates` returns 200
- existing `/api/repositories` still works
- existing `/api/segy-files` still works
- existing `/api/msi/viewer/managed-volumes-compatible` still works
- backend compile passes

Frontend build is not required unless frontend changes.

No conversion test should be run in the first façade block.

---

## Non-Goals

Do not:

- remove existing SR routes
- remove existing EDR routes
- change conversion behavior
- change MSI registration behavior
- move Managed Data into Source Intake
- patch frontend display logic
- perform data cleanup
- run bulk conversion

---

## Expected Outcome

After the first façade block, the application should have a new backend route family:

- `/api/source-intake/...`

This route family will provide the stable API target for later UI consolidation.

The existing UI should continue working.
