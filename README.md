# MultiViewer Well Log Viewer

**Branch:** wl-build-001-scaffold-implementation  
**Sprint:** WL-BUILD-001 — MSI-Integrated Scaffold  
**Status:** Scaffold — not yet functional

---

## Architecture

The Well Log Viewer is an MSI-integrated MultiViewer module.

```
LAS source file
  -> backend well import service
    -> MSI dataset/source/representation registration
      -> backend well_viewer_package_service
        -> frontend equinorWellLogAdapter
          -> @equinor/videx-wellog renderer
```

**MSI is the backend authority.** The frontend renders backend-owned contracts only.

---

## Rendering dependency

- `@equinor/videx-wellog` — frontend rendering component library only
- `webviz-subsurface-components` — **NOT used** as product scaffold

---

## Backend

```
backend/app/wells/
  __init__.py
  models.py                     — Pydantic domain models; well_multitrack_v1 contract
  las_import_service.py         — LAS import service (placeholder — WL-BUILD-002)
  well_qaqc_service.py          — QAQC service with initial finding codes
  well_viewer_package_service.py — Generates well_multitrack_v1 packages
  msi_well_adapter.py           — MSI boundary adapter
  api_wells.py                  — FastAPI routes (delegate to services)

backend/tests/wells/
  test_las_import_service.py
  test_well_qaqc_service.py
  test_well_viewer_package_service.py
  test_msi_well_adapter.py
```

### Run backend tests

```bash
cd <repo-root>
PYTHONPATH=. pytest backend/tests/wells -q
```

---

## Frontend

```
frontend/src/wells/
  types.ts                              — TypeScript types (well_multitrack_v1)
  WellLogViewerPage.tsx                 — Page-level component
  adapters/equinorWellLogAdapter.ts     — ONLY translation boundary to ViDEx
  components/MultiViewerWellLogViewer.tsx
  components/WellQaqcPanel.tsx
  components/WellTrackToolbar.tsx

frontend/src/shared/
  ui/       — MultiViewer shared UI components
  styles/   — MultiViewer shared styles
```

### Run frontend typecheck

```bash
cd frontend
npm install
npm run typecheck
```

---

## Governance

- `docs/governance/WLV_BUILD_RULES.md` — build rules
- `docs/contracts/well_multitrack_v1.md` — canonical contract
- `docs/sprints/WL_BUILD_001_SCAFFOLD_CONTROL_PACK.md` — sprint control pack

---

## What is NOT in this scaffold (deferred)

- Full LAS parser (`lasio` wiring)
- Full QAQC rule engine
- ViDEx component rendering (track/curve display)
- MSI client integration
- Managed Data page
- Source Intake page
- Raster logs, core images, deviation surveys
- TVD/TVDSS transforms
