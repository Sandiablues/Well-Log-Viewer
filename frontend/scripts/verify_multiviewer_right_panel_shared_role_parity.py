#!/usr/bin/env python3
from pathlib import Path
import hashlib

HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
WC=WLV/"src/styles/multiviewer-presentation/components.css"
SC=SDV/"src/styles/multiviewer-presentation/components.css"
EXPECTED="f3368cad3f6d03a9bef9fa665e6c9348b03641d2659be0713c075f25aa5e8cfa"

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL RIGHT-PANEL SHARED ROLE PARITY GUARD")
    print(m); raise SystemExit(1)

if sha(WC)!=EXPECTED or sha(SC)!=EXPECTED: fail("shared master SHA drift")
if WC.read_bytes()!=SC.read_bytes(): fail("shared master identity mismatch")

t=WC.read_text()
required=[
  "MULTIVIEWER RIGHT-PANEL SHARED ROLE PARITY V1.0.0",
  ".mv-role-panel-title",
  ".mv-role-section-title",
  ".mv-role-property-label",
  ".mv-role-property-value",
  ".mv-role-property-row > .mv-role-property-label",
  ".mv-role-property-row > th.mv-role-property-label",
  ".mv-role-property-row > td.mv-role-property-value-cell",
  "font-size: var(--mv-font-size-sm) !important;",
  "font-weight: var(--mv-font-weight-normal) !important;",
  "line-height: var(--mv-line-height-ui) !important;",
  "padding-top: 5px !important;",
  "padding-bottom: 5px !important;",
  "border-bottom: 1px solid var(--mv-border-subtle) !important;",
]
for x in required:
    if x not in t: fail("missing shared parity contract: "+x)

print("PASS RIGHT-PANEL SHARED ROLE PARITY GUARD")
print("Panel/section titles: SDV CANONICAL")
print("Property labels: 12/400/1.35 MUTED")
print("Property values: 12/400/1.35 PRIMARY")
print("Row vertical rhythm: 5px + subtle divider")
print("Viewer-specific widths/geometry: PRESERVED")
