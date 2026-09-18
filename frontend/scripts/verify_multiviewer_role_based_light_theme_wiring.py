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
def fail(m):
    print("FAIL MULTIVIEWER ROLE-BASED LIGHT THEME WIRING GUARD")
    print(m)
    raise SystemExit(1)

for p in [WT,ST]:
    if not p.is_file() or sha(p)!=EXPECTED:
        fail("theme.css drift: "+str(p))
if WT.read_bytes()!=ST.read_bytes():
    fail("WLV/SDV shared theme identity mismatch")

text=WT.read_text()
required=[
    "MULTIVIEWER ROLE-BASED LIGHT THEME WIRING V1.0.0",
    'html[data-mv-theme="light"] .wlv-demo-shell',
    'html[data-mv-theme="light"] .wlv-track-toolbar',
    'html[data-mv-theme="light"] .wlv-managed-inventory-page',
    '--mdp-page-bg: var(--mv-bg-app) !important;',
    'html[data-mv-theme="light"] .wlv-source-intake',
    '--wlv-si-bg: var(--mv-bg-app);',
    'html[data-mv-theme="light"] .wlv-toolbox-page',
    'html[data-mv-theme="light"] .wlv-kr-workbench',
    'html[data-mv-theme="light"] .wlv-wbv-page',
    'html[data-mv-theme="light"] .mv-app',
    "Explicit WDV scientific exclusion",
    "Explicit WBV science exclusion",
    "Explicit SDV science exclusion",
    '[data-mv-theme="light"]',
    '.mv-theme-toggle {',
    '--mv-bg-app: #dce3e9;',
]
for item in required:
    if item not in text:
        fail("role wiring contract missing: "+item)

print("PASS MULTIVIEWER ROLE-BASED LIGHT THEME WIRING GUARD")
print("WLV/SDV theme.css identity: EXACT")
print("Global shell/nav light roles: PRESENT")
print("WDV chrome roles: PRESENT; scientific canvas EXCLUDED")
print("Managed Data role variables: LIGHT OVERRIDES PRESENT")
print("Source Intake role variables: LIGHT OVERRIDES PRESENT")
print("Toolbox / Knowledge neutral shell: LIGHT OVERRIDES PRESENT")
print("WBV chrome roles: PRESENT; 3D science EXCLUDED")
print("SDV chrome roles: PRESENT; seismic science EXCLUDED")
print("Semantic/status colors: NOT GENERICALLY OVERRIDDEN")
