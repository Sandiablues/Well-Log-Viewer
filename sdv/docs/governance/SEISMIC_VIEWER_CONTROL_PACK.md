# Seismic Viewer Control Pack

## Active Project Path

The active launcher-bound working app is:

~/Applications/MultiViewer/seismic_viewer_project

Do not treat the Desktop copy as live unless explicitly instructed:

~/Desktop/Seismic_Viewer/seismic_viewer_project

## Launcher Rule

Do not modify the launcher chain unless the block is explicitly a launcher-repair block.

## Architecture Direction

The desktop app is a single-node deployment profile of an enterprise-shaped architecture.

Preserve boundaries around:

- Viewer UI
- Backend API
- Metadata Service Layer
- Report Service
- Ingestion / Worker Service
- Storage Layer
- MSI / Managed Source Inventory
- Ops / Runtime scripts

## MSI / Managed Data Rules

The MSI service owns managed representations, lifecycle semantics, and viewer availability state.

Managed Data semantics:

- Nothing appears in the viewer Select Data dropdown by default.
- Load makes a managed representation available to the viewer.
- Unload removes it from viewer selection/dropdown but keeps it visible in Managed Data.
- Delete removes it from the Managed Data registry.
- Fully converted data normally supersedes preview.
- Preview remains available as fallback, QA, or manual option.

## Source Intake / QAQC Rule

Source Intake is not a generic catalogue.

Discovery, classification, load-sheet generation, metadata/evidence matching, and QAQC state should be backend-owned contracts.

## 2D / 3D Separation

Backend classification should drive 2D line candidates, 3D volume candidates, excluded records, review-required records, and conversion gating.

Frontend must not rely on ad hoc file-name or UI-only 2D/3D inference where backend classification exists.

## Stop Rule

Stop immediately if a second micro-patch is being considered, frontend inference is being added, lifecycle truth is unclear, ownership is ambiguous, or a large file needs fragile surgery.
