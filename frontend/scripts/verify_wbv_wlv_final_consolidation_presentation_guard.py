#!/usr/bin/env python3
from pathlib import Path
ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"
CSS=ROOT/"src/wells/wbv/Wellbore3DPage.css"
def fail(msg):
    print("FAIL WBV/WLV FINAL CONSOLIDATION PRESENTATION GUARD")
    print(msg); raise SystemExit(1)
master=MASTER.read_text(); css=CSS.read_text()
marker="MULTIVIEWER MASTER WBV/WLV FINAL INFORMATION / GEOMETRY CHROME V1.0.0"
if marker not in master: fail("missing Phase 36 master block")
for s in [
    ":where(.mv-ui-scope) .wlv-wbv-information-menu > summary",
    ":where(.mv-ui-scope) .wlv-wbv-information-menu__body",
    ":where(.mv-ui-scope) .wlv-wbv-qaqc-summary strong",
    ":where(.mv-ui-scope) .wlv-wbv-geometry-table",
    ":where(.mv-ui-scope) .wlv-wbv-geometry-table__header span",
]:
    if s not in master: fail("missing master selector: "+s)
for s in [
    ".wlv-wbv-information-menu__body {\n  position: absolute;",
    "width: min(420px, calc(100vw - 3rem));",
    ".wlv-wbv-geometry-table__row {\n  display: grid;",
    "grid-template-columns: minmax(68px, 0.7fr) minmax(84px, 1fr) minmax(84px, 1fr);",
    ".wlv-wbv-panel--left .wlv-wbv-view-controls",
    ".wlv-wbv-panel--right .wlv-wbv-interval-actions",
]:
    if s not in css: fail("local geometry/accepted boundary missing: "+s)
print("PASS WBV/WLV FINAL CONSOLIDATION PRESENTATION GUARD")
print("Information menu neutral chrome: MASTER/PRESENT")
print("QA/QC summary neutral typography: MASTER/PRESENT")
print("Geometry table neutral chrome: MASTER/PRESENT")
print("Information/table geometry: LOCAL/PRESERVED")
print("WBV View compact contract: LOCAL/PRESERVED")
print("WBV Core/Interval contract: LOCAL/PRESERVED")
