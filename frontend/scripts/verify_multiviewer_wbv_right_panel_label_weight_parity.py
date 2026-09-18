#!/usr/bin/env python3
from pathlib import Path
import hashlib
HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
WC=WLV/"src/styles/multiviewer-presentation/components.css"
SC=SDV/"src/styles/multiviewer-presentation/components.css"
EXPECTED='f3368cad3f6d03a9bef9fa665e6c9348b03641d2659be0713c075f25aa5e8cfa'
REQUIRED='/* WBV right-panel metadata labels follow SDV canonical property-label grammar. */\n.mv-ui-scope .wlv-wbv-well-summary__row > span,\n.mv-ui-scope .wlv-wbv-trajectory-list__row > span {\n  font-size: 12px !important;\n  font-weight: 400 !important;\n  line-height: 16.2px !important;\n}'
LEGACY='.mv-ui-scope .wlv-wbv-well-summary__row > span,\n.mv-ui-scope .wlv-wbv-trajectory-list__row > span,\n.mv-ui-scope .wlv-wbv-field > label {\n  font-size: 12px !important;\n  font-weight: 600 !important;\n  line-height: 14.4px !important;\n}'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL WBV RIGHT-PANEL LABEL WEIGHT PARITY GUARD")
    print(m)
    raise SystemExit(1)

if sha(WC)!=EXPECTED or sha(SC)!=EXPECTED:
    fail("shared master SHA drift")
if WC.read_bytes()!=SC.read_bytes():
    fail("shared master identity mismatch")
t=WC.read_text()
if REQUIRED not in t:
    fail("12/400/16.2 WBV metadata-label contract missing")
if LEGACY in t:
    fail("legacy 600-weight combined WBV metadata rule returned")

print("PASS WBV RIGHT-PANEL LABEL WEIGHT PARITY GUARD")
print("Summary metadata labels: 12/400/16.2")
print("Trajectory metadata labels: 12/400/16.2")
print("Non-right-panel field labels: PRESERVED")
