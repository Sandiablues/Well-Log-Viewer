# Restore Seismic Viewer / MultiViewer From Git

This Git branch is intended to be a complete restorable source backup.

It excludes runtime/generated/seismic data:
SEG-Y, SGY, Zarr, uploads, jobs, logs, venv, node_modules, frontend dist,
and backend packaged_dist.

## Restore

Run these commands from a clean machine or clean folder:

    mkdir -p "$HOME/Applications/MultiViewer"
    cd "$HOME/Applications/MultiViewer"
    git clone git@github.com:Sandiablues/Multi-Viewer.git seismic_viewer_project
    cd seismic_viewer_project
    git checkout <restorable-backup-branch>
    bash scripts/runtime/restore_from_git.sh

After restore, reload seismic test/demo data through the application.
