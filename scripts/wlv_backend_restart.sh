#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/wlv_backend_stop.sh"
"$SCRIPT_DIR/wlv_backend_start.sh"
