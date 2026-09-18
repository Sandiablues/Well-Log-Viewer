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
    print("FAIL MULTIVIEWER PHASE41D SDV CASCADE AUTHORITY GUARD"); print(m); raise SystemExit(1)
for p in [WC,SC]:
    if not p.is_file() or sha(p)!=EXPECTED: fail("components.css drift: "+str(p))
if WC.read_bytes()!=SC.read_bytes(): fail("shared components identity mismatch")
text=WC.read_text()
required=[
 "MULTIVIEWER PHASE 41D — SDV CASCADE-AUTHORITY REPAIR V1.0.0",
 ".mv-ui-scope .wlv-demo-nav-item",
 "height: 64px !important;",
 "font-size: 11px !important;",
 ".mv-ui-scope .wlv-toolbar-zone-header",
 "font-size: 12px !important;",
 "font-weight: 600 !important;",
 ".mv-ui-scope .wlv-inventory-section-toggle",
 ".mv-ui-scope .wlv-wbv-view-controls button",
]
for x in required:
    if x not in text: fail("missing cascade contract: "+x)
required_wbv_label_block = '/* WBV right-panel metadata labels follow SDV canonical property-label grammar. */\n.mv-ui-scope .wlv-wbv-well-summary__row > span,\n.mv-ui-scope .wlv-wbv-trajectory-list__row > span {\n  font-size: 12px !important;\n  font-weight: 400 !important;\n  line-height: 16.2px !important;\n}\n\n/* Preserve field-label treatment outside the normalized right panel. */\n.mv-ui-scope .wlv-wbv-field > label {\n  font-size: 12px !important;\n  font-weight: 600 !important;\n  line-height: 14.4px !important;\n}'
if required_wbv_label_block not in text:
    fail("WBV right-panel metadata labels are not SDV canonical 12/400/16.2")

print("PASS MULTIVIEWER PHASE41D SDV CASCADE AUTHORITY GUARD")
print("Live cascade defect: OVERRIDDEN")
print("WLV/WBV role selectors: HIGHER AUTHORITY")
print("SDV canonical type/control grammar: PRESENT")
print("WDV Lock/Tie semantic boundary: PRESERVED")
print("WBV View/Interval geometry: PRESERVED")
