#!/usr/bin/env python3
from pathlib import Path
import hashlib

HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
WT=WLV/"src/styles/multiviewer-presentation/theme.css"
ST=SDV/"src/styles/multiviewer-presentation/theme.css"

EXPECTED='42948d0b0f6dffd2405f53889272f202ac2b0a7c4f55faf79f2a4575b8ce8b54'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL MULTIVIEWER MASTER THEME AUTHORITY GUARD")
    print(m)
    raise SystemExit(1)

for p in [WT,ST]:
    if not p.is_file():
        fail("missing shared theme.css")
    if sha(p)!=EXPECTED:
        fail("theme.css SHA drift: "+str(p))

if WT.read_bytes()!=ST.read_bytes():
    fail("WLV/SDV theme.css identity mismatch")

text=WT.read_text()

for token in [
    "--mv-bg-app:",
    "--mv-surface-1:",
    "--mv-text-primary:",
    "--mv-border-normal:",
    "--mv-chrome-panel-bg:",
    "--mv-chrome-menu-bg:",
    "--mv-chrome-popover-bg:",
    "--mv-chrome-modal-bg:",
    "--mv-chrome-table-header-bg:",
    "--mv-chrome-focus:",
    "--mv-chrome-shadow:",
]:
    if text.count(token) < 2:
        fail("token missing from dark/light contract: "+token)

for exact in [
    "--mv-bg-app: #0d1116;",
    "--mv-bg-canvas: #0d1116;",
    "--mv-surface-1: #101820;",
    "--mv-text-primary: #e3e8ec;",
    "--mv-border-normal: #354452;",
    "--mv-control-bg: #091118;",
]:
    if exact not in text:
        fail("accepted dark value drift: "+exact)

for required in [
    '[data-mv-theme="light"]',
    "color-scheme: light;",
    "color-scheme: dark;",
    "MULTIVIEWER GLOBAL THEME TOGGLE V1.0.0",
    "MULTIVIEWER ROLE-BASED LIGHT THEME WIRING V1.0.0",
    "MULTIVIEWER LIGHT PALETTE REBALANCE V1.0.0",
    "MULTIVIEWER MULTI-GREY CONTRAST PALETTE V1.0.0",
    "MULTIVIEWER DARKER MULTI-GREY DEPTH CONTRAST V1.0.0",
    "MULTIVIEWER LIGHT THEME DEPTH & ELEVATION ROLES V1.0.0",
    ".mv-theme-toggle {",
    "background: var(--mv-chrome-panel-bg);",
    "color: var(--mv-chrome-text);",
]:
    if required not in text:
        fail("Phase40 theme authority contract missing: "+required)

print("PASS MULTIVIEWER MASTER THEME AUTHORITY GUARD")
print("WLV/SDV shared theme identity: EXACT")
print("Accepted dark base palette: PRESERVED")
print("Canonical light neutral palette: PRESENT")
print("Semantic neutral chrome roles: PRESENT")
print("Global theme-toggle neutral chrome: PRESENT")
print("Scientific/semantic palette ownership: EXCLUDED/PRESERVED")
