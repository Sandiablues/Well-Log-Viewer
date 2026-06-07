# WL-BUILD-001 CTO.ai / Claude Implementation Prompt

You are implementing WL-BUILD-001 for the MultiViewer Well Log Viewer /
Wellbore Data QAQC project.

Read and obey:

- docs/governance/WLV_BUILD_RULES.md
- docs/contracts/well_multitrack_v1.md
- docs/sprints/WL_BUILD_001_SCAFFOLD_CONTROL_PACK.md

## Task

Create the initial MSI-integrated Well Log Viewer scaffold.

This is a scaffold sprint only.

Do not implement a full working viewer.

## Architecture

The Well Log Viewer must be an MSI-backed MultiViewer module.

MSI remains the backend authority for dataset identity, source file identity,
artifact identity, representation identity, lifecycle state, viewer availability,
QAQC attachment points, delete/unload semantics, and source-to-derived
relationships.

Equinor ViDEx is only a frontend rendering dependency.

Use:

- `@equinor/videx-wellog`

Do not use:

- `webviz-subsurface-components` as product scaffold
- Webviz/Dash architecture
- frontend LAS parsing
- frontend QAQC inference
- frontend lifecycle ownership

## Required backend scaffold

Create:

backend/app/wells/__init__.py
backend/app/wells/models.py
backend/app/wells/las_import_service.py
backend/app/wells/well_qaqc_service.py
backend/app/wells/well_viewer_package_service.py
backend/app/wells/msi_well_adapter.py
backend/app/wells/api_wells.py

Create:

backend/tests/wells/test_las_import_service.py
backend/tests/wells/test_well_qaqc_service.py
backend/tests/wells/test_well_viewer_package_service.py
backend/tests/wells/test_msi_well_adapter.py

Backend files should contain durable service skeletons, not heavy implementation.

Routes must delegate to services.

## Required frontend scaffold

Create:

frontend/src/wells/WellLogViewerPage.tsx
frontend/src/wells/types.ts
frontend/src/wells/adapters/equinorWellLogAdapter.ts
frontend/src/wells/components/MultiViewerWellLogViewer.tsx
frontend/src/wells/components/WellQaqcPanel.tsx
frontend/src/wells/components/WellTrackToolbar.tsx

Create shared directories if needed:

frontend/src/shared/ui/
frontend/src/shared/styles/

Frontend types must reflect the backend-owned well_multitrack_v1 contract.

The Equinor adapter must be the only place where MultiViewer viewer packages are
translated into ViDEx-facing props/config/data.

## Dependency handling

Add `@equinor/videx-wellog` to the frontend dependency manifest if a frontend
package manifest exists.

Do not add `webviz-subsurface-components`.

Do not copy Equinor source code into the repo.

Do not copy Webviz source code into the repo.

## Documentation updates

Update:

README.md
docs/contracts/well_multitrack_v1.md
docs/governance/WLV_BUILD_RULES.md

The docs must preserve the MSI/backend authority rule.

## Tests/build

Run the safest available checks for the scaffold.

At minimum, report:

- backend test command attempted or why unavailable
- frontend build/typecheck command attempted or why unavailable
- dependency install command attempted or why unavailable

Do not hide failures.

## Output required

Return:

1. Changed file list.
2. Dependency changes.
3. Test/build output.
4. Confirmation that ViDEx is adapter-wrapped only.
5. Confirmation that Webviz was not added.
6. Confirmation that no frontend LAS parsing was added.
7. Confirmation that MSI remains backend authority.
8. Any unresolved risks.
