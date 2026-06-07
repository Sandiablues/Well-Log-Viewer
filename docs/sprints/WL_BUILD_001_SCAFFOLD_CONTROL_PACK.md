# WL-BUILD-001 — MSI-Integrated Well Log Viewer Scaffold

## Sprint type

Feature scaffold / architecture foundation.

No product behavior beyond placeholder wiring.

## Objective

Create the initial MultiViewer Well Log Viewer / Wellbore Data QAQC module
scaffold.

The scaffold must establish clean backend, frontend, MSI, viewer-package, QAQC,
and Equinor ViDEx adapter boundaries.

This sprint must not attempt to build a full working viewer.

## Project context

The Well Log Viewer is part of the broader MultiViewer product.

It is being developed separately from the active Seismic Viewer for now, but it
must remain aligned with the shared MultiViewer architecture, governance model,
UI language, and future integration path.

The backend foundation must use the MSI / Managed Source Inventory concept.

## Source dependency decision

Primary rendering dependency:

- `@equinor/videx-wellog`
- Version observed in WL-BUILD-000: `1.4.2`
- License: MIT
- Role: frontend rendering component library only

Reference-only repository:

- `equinor/webviz-subsurface-components`
- Role: example/reference only
- Do not use as product scaffold
- Do not adopt Webviz/Dash architecture

## Non-negotiable architecture rule

MSI remains the backend authority.

Equinor ViDEx is only the frontend rendering layer.

Correct flow:

LAS source file
  -> backend well import service
    -> MSI dataset/source/representation registration
      -> backend well_multitrack_v1 viewer package
        -> frontend MultiViewer adapter
          -> @equinor/videx-wellog renderer

Incorrect flow:

LAS file
  -> frontend ViDEx model
    -> frontend lifecycle state
      -> later attempt to retrofit MSI

The incorrect flow is prohibited.

## Backend ownership

Backend owns:

- LAS parsing
- Curve extraction
- Curve metadata
- Null handling
- Well-log QAQC findings
- MSI dataset/source/artifact/representation registration
- Viewer package generation
- Dataset lifecycle state
- Viewer availability
- Delete/unload semantics

## Frontend ownership

Frontend owns:

- Fetching backend-owned viewer packages
- Rendering backend-owned contracts
- Adapter translation into ViDEx props/config
- Display interactions
- Panel layout
- QAQC findings display

Frontend must not:

- Parse LAS
- Infer QAQC
- Own lifecycle state
- Invent canonical well-log data models
- Make ViDEx props the backend API contract

## Equinor ViDEx ownership

ViDEx owns only:

- Track rendering
- Depth-aligned display
- Visual interaction primitives
- Plot/scale rendering

ViDEx must remain behind a MultiViewer adapter.

## Required backend scaffold

Create:

backend/app/wells/
  __init__.py
  models.py
  las_import_service.py
  well_qaqc_service.py
  well_viewer_package_service.py
  msi_well_adapter.py
  api_wells.py

Required intent:

- `models.py`
  Defines Pydantic/domain models for well, wellbore, curve, curve set,
  QAQC finding, MSI references, and well_multitrack_v1 package objects.

- `las_import_service.py`
  Placeholder service for future LAS parsing.
  No frontend parsing.
  May define service class/function skeleton only.

- `well_qaqc_service.py`
  Placeholder deterministic QAQC service.
  May define initial finding codes, but no heavy rules yet.

- `well_viewer_package_service.py`
  Placeholder service that will generate well_multitrack_v1 packages from
  backend-owned representations.

- `msi_well_adapter.py`
  Placeholder adapter between well-domain services and MSI-managed dataset,
  source, artifact, representation, lifecycle, and viewer availability records.

- `api_wells.py`
  Placeholder FastAPI route module.
  Routes must delegate to services.
  No business logic in route bodies.

## Required backend tests scaffold

Create:

backend/tests/wells/
  test_las_import_service.py
  test_well_qaqc_service.py
  test_well_viewer_package_service.py
  test_msi_well_adapter.py

Initial tests may validate placeholders, importability, contract shapes, and
service boundaries.

## Required frontend scaffold

Create:

frontend/src/wells/
  WellLogViewerPage.tsx
  types.ts
  adapters/equinorWellLogAdapter.ts
  components/MultiViewerWellLogViewer.tsx
  components/WellQaqcPanel.tsx
  components/WellTrackToolbar.tsx

Required intent:

- `types.ts`
  Defines TypeScript types matching well_multitrack_v1.

- `adapters/equinorWellLogAdapter.ts`
  Converts MultiViewer well_multitrack_v1 into the shape expected by
  @equinor/videx-wellog.

- `MultiViewerWellLogViewer.tsx`
  Shell component that receives backend-owned viewer package data and renders
  through the adapter.

- `WellLogViewerPage.tsx`
  Page-level component placeholder.

- `WellQaqcPanel.tsx`
  Displays backend-provided QAQC findings.

- `WellTrackToolbar.tsx`
  Placeholder toolbar using MultiViewer UI conventions.

## Shared UI scaffold

Create shared UI/style directories only if not already present:

frontend/src/shared/
  ui/
  styles/

Do not create a separate visual language for the Well Log Viewer.

Use MultiViewer style principles:

- Consistent panel/card layout
- Consistent toolbar/action layout
- Consistent status/error/loading states
- No filled colored executable buttons
- Colored action controls should use colored outline and colored text only

## Dependencies

Frontend package dependency:

- `@equinor/videx-wellog`

Do not add `webviz-subsurface-components` as a dependency.

Backend dependency to consider later:

- `lasio`

Do not add `lasio` unless WL-BUILD-001 includes explicit backend dependency
setup and import tests. This sprint may leave LAS parsing as a placeholder.

## Required docs updates

Update or create:

docs/contracts/well_multitrack_v1.md
docs/governance/WLV_BUILD_RULES.md
README.md

Do not remove existing WL-BUILD-000 source review artifacts.

## Prohibited in this sprint

Do not implement:

- Full LAS parser
- Full QAQC engine
- Managed Data page
- Source Intake page
- Raster logs
- Core images
- Deviation surveys
- TVD/TVDSS/TWT transforms
- Synthetic seismograms
- Seismic integration
- Sectional/correlation viewer
- 3D borehole viewer
- Hard-coded GR/resistivity/density display logic in React
- Frontend-owned lifecycle state
- Frontend LAS parsing

## Acceptance criteria

Pass only if:

1. Scaffold files exist in the required locations.
2. Backend service boundaries are clear.
3. MSI adapter exists as a first-class backend boundary.
4. well_multitrack_v1 remains the canonical viewer package.
5. Equinor ViDEx is isolated behind an adapter.
6. Frontend does not parse LAS.
7. Frontend does not infer QAQC.
8. Frontend does not own lifecycle state.
9. Webviz is not used as the product base.
10. Build/test placeholders are present.
11. No seismic-specific MSI fields are misused for wells.
12. The scaffold can be reviewed without running the full application.

## Stop conditions

Stop and report instead of coding further if:

- Existing repo structure conflicts with this scaffold.
- MSI ownership cannot be represented cleanly.
- The proposed adapter would require ViDEx to become the backend contract.
- Frontend would need to parse LAS to render.
- Well-specific lifecycle state would be stored in React.
- The task expands into full viewer implementation.
- The scaffold requires copying large external source trees into the repo.

## Expected result bundle

The implementer must return:

- Changed file list
- Summary of scaffold structure
- Confirmation of dependency changes
- Confirmation that Webviz was not added
- Confirmation that ViDEx is adapter-wrapped only
- Test/build commands run
- Failures or unresolved issues
- Stop-condition notes, if any
