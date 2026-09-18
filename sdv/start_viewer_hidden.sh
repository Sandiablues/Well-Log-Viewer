#!/bin/bash
set -euo pipefail

# Backward-compatible alias.
# Starts backend if needed and opens browser.
PROJECT_ROOT="$HOME/Desktop/Seismic_Viewer/seismic_viewer_project"
"$PROJECT_ROOT/launch_viewer_hidden.sh"
