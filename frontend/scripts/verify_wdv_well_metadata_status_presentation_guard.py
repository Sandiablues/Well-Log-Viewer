#!/usr/bin/env python3
from pathlib import Path

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"
TRACK=ROOT/"src/styles/track-layout-prototype.css"

def fail(msg):
    print("FAIL WDV WELL METADATA / STATUS PRESENTATION GUARD")
    print(msg)
    raise SystemExit(1)

master=MASTER.read_text()
track=TRACK.read_text()

marker="MULTIVIEWER MASTER WDV WELL METADATA / STATUS FOOTER CHROME V1.0.0"
if marker not in master:
    fail("missing Phase 29 master marker")

start=master.find(marker)
b0=master.rfind("/*",0,start)
b1=master.find("/* ==========================================================================",start+len(marker))
block=master[b0:b1 if b1>=0 else len(master)]
if ":where(.mv-ui-scope)" not in block:
    fail("Phase 29 block lacks mv-ui-scope")
if ".mv-app .wlv-" in block:
    fail("Phase 29 block contains forbidden .mv-app WDV scope")

for selector in [
    ":where(.mv-ui-scope) .well-header dt",
    ":where(.mv-ui-scope) .well-header dd",
    ":where(.mv-ui-scope) .wlv-status-footer",
]:
    if selector not in block:
        fail(f"missing master selector: {selector}")

# Local geometry/type-size ownership established by Phase 29.
local_contract=[
    ".well-header dl {\n  display: grid;",
    "grid-template-columns: 74px 1fr;",
    "gap: 5px 9px;",
    "font-size: 12px;",
    "line-height: 1.25;",
    ".well-header dd {\n  margin: 0;",
    ".wlv-status-footer {\n  height: 28px;",
    "display: flex;",
    "align-items: center;",
    "gap: 24px;",
    "padding: 0 12px;",
    "font-size: 11px;",
]
for needle in local_contract:
    if needle not in track:
        fail(f"local geometry/type-size contract missing: {needle}")

# Prevent duplicate neutral authority from returning locally.
for forbidden in [
    ".well-header dt {\n  color: #a1a1aa;\n  font-weight: 400;",
    ".well-header dd {\n  color: #d4d4d8;\n  font-weight: 400;",
    ".wlv-status-footer {\n  border-top: 1px solid #2d2d2d;\n  background: #151515;\n  color: #8b8b8b;",
]:
    if forbidden in track:
        fail(f"duplicate local neutral authority reintroduced: {forbidden}")

# Critical exclusion: WDV track-header and Lock/Tie contracts must remain local/present.
protected_header_contract=[
    ".wlv-track-header {",
    ".wlv-track-title-row {",
    ".wlv-track-placement-selector[data-combination-track-state='locked']",
    ".wlv-track-placement-selector[data-viewport-tied='true']",
    ".wlv-track-placement-selector[data-viewport-tie-role='leader']",
    ".wlv-toolbar-group-view .wlv-viewport-tie-toggle-button.tied",
]
for needle in protected_header_contract:
    if needle not in track:
        fail(f"protected WDV header/Lock-Tie contract missing: {needle}")

print("PASS WDV WELL METADATA / STATUS PRESENTATION GUARD")
print("Well metadata label/value neutral presentation: MASTER/PRESENT")
print("Status-footer neutral chrome: MASTER/PRESENT")
print("Well metadata/footer geometry: LOCAL/PRESERVED")
print("WDV track-header / Lock-Tie presentation boundary: LOCAL/PRESERVED")
