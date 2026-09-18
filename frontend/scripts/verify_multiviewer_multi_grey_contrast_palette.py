#!/usr/bin/env python3
from pathlib import Path
import hashlib
HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
WT=WLV/"src/styles/multiviewer-presentation/theme.css"
ST=SDV/"src/styles/multiviewer-presentation/theme.css"
EXPECTED="42948d0b0f6dffd2405f53889272f202ac2b0a7c4f55faf79f2a4575b8ce8b54"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def check_identity(label):
    for p in [WT,ST]:
        if not p.is_file() or sha(p)!=EXPECTED:
            print("FAIL "+label); print("theme.css drift: "+str(p)); raise SystemExit(1)
    if WT.read_bytes()!=ST.read_bytes():
        print("FAIL "+label); print("WLV/SDV shared theme identity mismatch"); raise SystemExit(1)
    return WT.read_text()
t=check_identity("MULTIVIEWER MULTI-GREY CONTRAST PALETTE GUARD")
for x in ['--mv-surface-1: #f7f9fa;', '--mv-surface-2: #e8edf1;', '--mv-border-normal: #8b99a5;', '--mv-border-strong: #697987;', '--mv-chrome-table-header-bg: #e8edf1;']:
    if x not in t:
        print("FAIL MULTIVIEWER MULTI-GREY CONTRAST PALETTE GUARD"); print("contract missing: "+x); raise SystemExit(1)
print("PASS MULTIVIEWER MULTI-GREY CONTRAST PALETTE GUARD")
print('Current light candidate: TECHNICAL CONTRAST')
print('Panel hierarchy: STRENGTHENED')
print('Scientific dark surfaces: EXCLUDED/PRESERVED')
