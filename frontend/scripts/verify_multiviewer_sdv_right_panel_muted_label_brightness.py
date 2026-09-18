#!/usr/bin/env python3
from pathlib import Path
import hashlib

HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
WC=WLV/"src/styles/multiviewer-presentation/components.css"
SC=SDV/"src/styles/multiviewer-presentation/components.css"
EXPECTED='f3368cad3f6d03a9bef9fa665e6c9348b03641d2659be0713c075f25aa5e8cfa'
MARKER='MULTIVIEWER SDV RIGHT-PANEL MUTED LABEL BRIGHTNESS NUDGE V1.0.3'
RULE='/* ==========================================================================\n   MULTIVIEWER SDV RIGHT-PANEL MUTED LABEL BRIGHTNESS NUDGE V1.0.3\n   Preserve existing muted-label typography. Brightness only is raised slightly.\n   Scope is the SDV viewer-info stack only; the global muted token is unchanged.\n   ========================================================================== */\n:where(.mv-app) .mv-viewer-info-stack .mv-viewer-info-card .mv-type-property-label,\n:where(.mv-app) .mv-viewer-info-stack .mv-viewer-info-row > .mv-type-property-label {\n  color: #aab4bd !important;\n}'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL SDV RIGHT-PANEL MUTED LABEL BRIGHTNESS GUARD")
    print(m)
    raise SystemExit(1)

if not WC.is_file() or not SC.is_file():
    fail("shared components.css missing")
if sha(WC)!=EXPECTED or sha(SC)!=EXPECTED:
    fail("shared master SHA drift")
if WC.read_bytes()!=SC.read_bytes():
    fail("shared master identity mismatch")

t=WC.read_text()
if MARKER not in t:
    fail("brightness marker missing")
if RULE not in t:
    fail("exact scoped brightness rule missing")
if t.count(MARKER)!=1:
    fail("brightness marker count is not exactly one")

# Guard the actual scope and ensure no global token replacement happened here.
if ":where(.mv-app) .mv-viewer-info-stack .mv-viewer-info-card .mv-type-property-label" not in t:
    fail("SDV viewer-info-stack scope missing")
if "color: #aab4bd !important;" not in t:
    fail("brightness value missing")

print("PASS SDV RIGHT-PANEL MUTED LABEL BRIGHTNESS GUARD")
print("Scope: SDV viewer-info-stack property labels")
print("Brightness: #aab4bd")
print("Typography/geometry: UNCHANGED")
print("Shared master identity: PRESERVED")
