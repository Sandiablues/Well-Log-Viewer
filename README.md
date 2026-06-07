# Well Log Viewer

MultiViewer Well Log Viewer / Wellbore Data QAQC module.

This project is part of the broader MultiViewer architecture. It is being
developed separately from the Seismic Viewer for now, but it must remain aligned
with the shared MultiViewer MSI, governance model, UI language, and future
integration path.

Primary Phase 1 objective:

- LAS-only MD-domain multitrack well-log viewer
- MSI-backed dataset/source/representation lifecycle
- Backend-owned LAS parsing, curve extraction, QAQC, and viewer packages
- Frontend adapter wrapping the Equinor ViDEx well-log renderer
