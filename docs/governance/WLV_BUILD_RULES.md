# MultiViewer Well Log Viewer Build Rules

**Version:** WL-BUILD-001  
**Status:** Active

The Well Log Viewer is an MSI-integrated MultiViewer module.

## Core rules

- MSI is the backend authority.
- Backend owns LAS parsing.
- Backend owns curve extraction.
- Backend owns curve metadata.
- Backend owns null handling.
- Backend owns well-log QAQC findings.
- Backend owns viewer package generation.
- Backend owns dataset/source/artifact/representation lifecycle.
- Backend owns viewer availability.
- Backend owns delete/unload semantics.
- Frontend renders backend-owned contracts only.
- Frontend must not parse LAS.
- Frontend must not infer QAQC.
- Frontend must not own lifecycle state.
- Equinor ViDEx must not become the canonical data model.

## Rendering dependency

Primary rendering dependency:

- `@equinor/videx-wellog`

Role: frontend rendering component library only.

Do not add `webviz-subsurface-components` as a dependency.  
Do not use Webviz/Dash architecture.  
Do not copy Equinor source trees into this repo.

## Canonical flow

```
LAS source file
  -> backend well import service
    -> MSI dataset/source/representation registration
      -> backend well_multitrack_v1 viewer package
        -> frontend MultiViewer adapter (equinorWellLogAdapter.ts)
          -> @equinor/videx-wellog renderer
```

## Prohibited in all sprints

- Frontend LAS parsing
- Frontend QAQC inference
- Frontend lifecycle state ownership
- ViDEx props as backend API contract
- webviz-subsurface-components as product scaffold
- Copying Equinor or Webviz source trees into the repo

## MultiViewer UI conventions

- Consistent panel/card layout
- Consistent toolbar/action layout
- Consistent status/error/loading states
- No filled colored executable buttons
- Colored action controls: colored outline + colored text only

## Sprint reference

| Sprint | Description |
|--------|-------------|
| WL-BUILD-000 | Diagnostic / source review (no product code) |
| WL-BUILD-001 | MSI-integrated scaffold |
| WL-BUILD-002+ | LAS import, viewer package assembly, ViDEx wiring |
