# WL-PROTOTYPE-001 — Track Layout Editor Working Template

This branch implements a frontend-only working prototype for the dbMap-style
MultiViewer Well Log Viewer track layout editor.

It is not production LAS ingestion, not backend persistence, and not final ViDEx
integration.

## Implemented prototype behaviors

- Uses track terminology only.
- Left curve inventory for loaded-well curves.
- Track toolbar with Add Track, Delete Track, Move Left, Move Right.
- Active track types: Depth Track and Curve Track.
- Reserved track types: Raster, Marker, Interval.
- Multiple depth tracks are allowed.
- Depth tracks can select MD, TVD, or TVDSS.
- Curve tracks can contain one or more curve assignments.
- Curve headers are stacked.
- Top curve header is front-dominant and front-most.
- Header order controls overpost order.
- Curve headers can be dragged within a track to reorder stack order.
- Curve headers can be dragged to another curve track.
- Curves can be dragged from the left curve inventory into a curve track.
- Front-dominant curve controls default lattice.
- User can override lattice to linear or logarithmic.
- Selected track properties appear in the right panel.
- Selected curve properties appear in the right panel.
- Right panel includes well header.
- Delete Track removes layout track only; it does not delete source curves.

## Production boundary reminders

The prototype uses local React state only.

Production implementation must keep backend/MSI authority over:

- source identity
- LAS parsing
- curve catalog
- layout validation
- layout/template persistence
- viewer package generation

