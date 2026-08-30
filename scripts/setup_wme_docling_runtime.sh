#!/bin/zsh
set -euo pipefail
PROJECT="${1:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
VENV="$PROJECT/runtime/wme_docling_venv"
MODELS="$PROJECT/runtime/models/docling"
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 is required" >&2; exit 1; }
mkdir -p "$PROJECT/runtime" "$MODELS"
[[ -d "$VENV" ]] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel setuptools
if [[ "$(uname -s)" == "Darwin" ]]; then python -m pip install "docling[ocrmac]" pandas tabulate; else python -m pip install docling pandas tabulate; fi
python -c 'import docling; from docling.document_converter import DocumentConverter; print("PASS: private document extraction runtime ready"); print("Provider: docling", getattr(docling, "__version__", "unknown"))'
