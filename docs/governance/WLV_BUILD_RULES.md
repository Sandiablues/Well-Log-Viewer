# MultiViewer Well Log Viewer Build Rules

The Well Log Viewer is an MSI-integrated MultiViewer module.

## Core rules

- MSI is the backend authority.
- Backend owns LAS parsing.
- Backend owns curve extraction.
- Backend owns well-log QAQC findings.
- Backend owns viewer package generation.
- Backend owns dataset/source/artifact/representation lifecycle.
- Frontend renders backend-owned contracts.
- Frontend must not parse LAS.
- Frontend must not infer QAQC.
- Frontend must not own lifecycle state.
- Equinor ViDEx must not become the canonical data model.

## Rendering dependency

Primary rendering dependency:

- @equinor/videx-wellog

Role:

- Frontend rendering component library only.

## Canonical flow

LAS source file
  -> backend well import service
    -> MSI dataset/source/representation registration
      -> backend well_multitrack_v1 viewer package
        -> frontend MultiViewer adapter
          -> @equinor/videx-wellog renderer

## Initial sprint

WL-BUILD-000 is diagnostic only.

It may inspect dependencies and generate review artifacts.

It must not scaffold product code.
