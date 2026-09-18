# Seismic Viewer Service Boundary Map

This document defines the near-term local architecture boundaries for Seismic Viewer.

The immediate purpose is to stop unrelated subsystems from cross-contaminating each other during local development, while preserving a path toward an enterprise deployable architecture.

## Current local runtime

Active live app path:

`~/Applications/MultiViewer/seismic_viewer_project`

Git/backup repo path:

`~/Desktop/Seismic_Viewer/seismic_viewer_project`

The Applications path is the live launcher-bound runtime.

The Desktop path is the Git/backup copy and must not be used for live development unless explicitly instructed.

## Boundary 1 — Frontend Viewer UI

Ownership:

`seismic-viewer-frontend/src`

Responsibilities:

- 2D viewer controls and rendering
- 3D viewer controls and rendering
- Data Manager UI
- Info panels
- Source browser UI
- Calls into backend APIs

Should not own:

- SEG-Y parsing
- Zarr conversion
- metadata scoring logic
- report rendering logic
- filesystem registry rules

## Boundary 2 — Backend API Route Layer

Ownership:

`seismic-viewer-backend/app/api`

Responsibilities:

- FastAPI routes
- Request/response handling
- Thin orchestration
- Delegation to services/report modules

Should not own:

- large inline HTML reports
- large inline CSS
- conversion internals
- scoring calculations beyond simple route glue
- frontend behavior

Accepted route pattern:

Routes should call service/report functions.

Example:

`render_volume_metadata_score_report(volume_id)`

## Boundary 3 — Report Service

Ownership:

`seismic-viewer-backend/app/reports`

Responsibilities:

- HTML report rendering
- shared report CSS
- report payload presentation
- report-specific helper formatting

Should not own:

- canonical metadata extraction
- document evidence scanning
- conversion jobs
- viewer slice serving
- frontend UI state

Accepted report module:

`app/reports/metadata_score_report.py`

Accepted CSS:

`app/reports/static/metadata_score_report.css`

## Boundary 4 — Metadata Summary / Scoring Services

Ownership:

`seismic-viewer-backend/app/services`

Current important service:

`metadata_summary_service.py`

Responsibilities:

- canonical metadata summary
- normalized metadata assembly
- metadata completeness
- evidence strength
- consistency status
- sidecar/header integration
- converted-volume metadata resolution

Report modules should consume this layer instead of guessing storage paths.

Important rule:

Converted volume reports must use:

`build_metadata_summary(volume_id)`

They must not assume:

`data/zarr/<volume_id>/viewer_metadata.json`

## Boundary 5 — Dataset Registry / Indexed SEG-Y Layer

Ownership:

`seismic-viewer-backend/app/api/datasets.py`

and related services.

Responsibilities:

- indexed SEG-Y dataset lookup
- indexed metadata summary
- indexed SEG-Y report route
- indexed SEG-Y preview support

Indexed SEG-Y metadata is provisional unless document/CRS/business validation is completed.

## Boundary 6 — Ingestion / Conversion / Worker Layer

Ownership:

Existing conversion and job-handling services/scripts.

Responsibilities:

- SEG-Y ingestion
- textual-header extraction
- binary-header sidecars
- trace-header sidecars
- SEG-Y indexing
- SEG-Y to optimized Zarr conversion
- job records
- temp-write and promotion logic

Should remain separable from:

- viewer rendering
- report layout
- frontend state
- launcher scripts

Future enterprise path:

This boundary should eventually become a worker service or worker container.

## Boundary 7 — Storage / Data Store Layer

Current local storage:

`seismic-viewer-backend/data`

Responsibilities:

- local Zarr data
- indexed SEG-Y records
- sidecars
- job records
- repository registry data

Future enterprise path:

This should be abstractable toward NAS/object storage without rewriting viewer/report logic.

## Boundary 8 — Runtime / Ops Layer

Ownership:

Launcher scripts, runtime identity, health checks, logs, PID files.

Current important files/routes:

- `/api/runtime/identity`
- `/api/runtime/routes`
- `~/Applications/MultiViewer/launch_multiviewer.sh`
- `docs/runtime/launch_multiviewer.sh.snapshot`
- `run/backend.pid`
- `logs/backend.log`

Responsibilities:

- start one backend only
- prevent duplicate listeners
- identify live runtime source files
- provide reliable local diagnostics
- preserve launcher stability

Critical rule:

There must be exactly one backend listener on port 8000.

## Do-not-cross rules

1. Frontend changes must not modify backend runtime launch behavior.
2. Report styling changes must not modify launcher behavior.
3. Report rendering must not live as large inline HTML/CSS inside API route files.
4. Converted-volume report logic must not assume direct filesystem paths.
5. Backend route files should stay thin.
6. Launcher scripts must guard against duplicate backend listeners.
7. Indexed SEG-Y metadata must remain labelled provisional until validated.
8. Technical readiness must not be confused with metadata maturity.

## Current accepted architectural hardening state

Accepted:

- E1 report-service extraction
- E1.2 runtime identity endpoint
- E1.4 launcher duplicate-backend guard
- E2.1 report/scoring contract documentation

Current restore-point commit:

`280f7f8 Complete E1 report service and runtime identity backup`

## Recommended next hardening direction

Next code-moving work should target the backend API layer carefully.

Priority candidates:

1. Keep report rendering isolated in `app/reports`.
2. Move more metadata scoring/summary logic into service functions, not routes.
3. Add health/identity checks to the normal development workflow.
4. Repair the normal GitHub backup script approved-file list before relying on it again.

Do not start containerization until the local service boundaries and backup process are reliable.
