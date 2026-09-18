#!/usr/bin/env python3
from pathlib import Path

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"
TRACK=ROOT/"src/styles/track-layout-prototype.css"

def fail(msg):
    print("FAIL WDV FINAL CONSOLIDATION PRESENTATION GUARD")
    print(msg)
    raise SystemExit(1)

master=MASTER.read_text()
track=TRACK.read_text()

marker="MULTIVIEWER MASTER WDV FINAL GENERIC POPOVER / EDITOR FOOTER CHROME V1.0.0"
if marker not in master:
    fail("missing Phase 35 final WDV master marker")

start=master.find(marker)
b0=master.rfind("/*",0,start)
b1=master.find("/* ============================================================================",start+len(marker))
block=master[b0:b1 if b1>=0 else len(master)]

for required in [
    ":where(.mv-ui-scope) .wlv-depth-command-popover",
    ":where(.mv-ui-scope) .wlv-saved-views-name-popover",
    ":where(.mv-ui-scope) .wlv-edit-track-modal-footer",
]:
    if required not in block:
        fail("missing final master selector: "+required)

if ".mv-app .wlv-" in block:
    fail("stale mv-app selector in final WDV master block")

local_contract=[
    ".wlv-depth-command-popover {\n  position: fixed;",
    "z-index: 2147483000;",
    ".wlv-depth-command-popover input:focus {\n  outline: none;",
    ".wlv-depth-command-popover button.primary {\n  border-color: #16a34a;",
    ".wlv-saved-views-name-popover {\n  position: absolute;",
    ".wlv-edit-track-modal-footer {\n  display: flex;",
    ".wlv-edit-track-modal-footer button.primary {\n  border-color: #18b783;",
    ".wlv-edit-track-modal-footer button.primary:disabled {\n  border-color: #46515e;",
    ".wlv-interval-builder-modal{position:fixed;",
    ".wlv-track-placement-selector[data-combination-track-state='locked']",
    ".wlv-track-placement-selector[data-viewport-tied='true']",
]
for needle in local_contract:
    if needle not in track:
        fail("local WDV boundary missing: "+needle)

print("PASS WDV FINAL CONSOLIDATION PRESENTATION GUARD")
print("Depth/range command neutral chrome: MASTER/PRESENT")
print("Saved Views naming neutral chrome: MASTER/PRESENT")
print("Edit Track footer neutral chrome: MASTER/PRESENT")
print("Popover/editor geometry and semantic states: LOCAL/PRESERVED")
print("Interval-builder/scientific editor presentation: LOCAL/EXCLUDED")
print("WDV track-header / Lock-Tie boundary: LOCAL/PRESERVED")
