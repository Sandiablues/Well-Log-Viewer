# Local Runtime Contract

The local desktop runtime must remain operational while architectural hardening proceeds.

## Active development path

`~/Applications/MultiViewer/seismic_viewer_project`

## Launcher / backup path

`~/Desktop/Seismic_Viewer/seismic_viewer_project`

Do not patch or build from the Desktop copy unless explicitly syncing to Git, repairing backup, or inspecting the launcher wrapper.

## Frozen launcher rule

Feature work must not modify:

- `Seismic Viewer.app`
- `start_viewer_hidden.sh`
- `launch_viewer_hidden.sh`

## Runtime checks

A hardening block is not accepted until these remain true:

- `/` returns HTML.
- `/api/datasets` returns JSON.
- Existing seismic rendering still works.
- Indexed SEG-Y metadata report opens as HTML.
- Converted Zarr metadata report opens as HTML.
