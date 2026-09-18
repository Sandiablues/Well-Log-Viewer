#!/usr/bin/env python3
from pathlib import Path

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"
TRACK=ROOT/"src/styles/track-layout-prototype.css"

def fail(msg):
    print("FAIL WDV CURVE HEADER ACTION MENU PRESENTATION GUARD")
    print(msg)
    raise SystemExit(1)

master=MASTER.read_text()
track=TRACK.read_text()

marker="MULTIVIEWER MASTER WDV CURVE HEADER ACTION MENU NEUTRAL CHROME V1.0.1"
if marker not in master:
    fail("missing Phase 33 V1.0.1 master marker")

start=master.find(marker)
b0=master.rfind("/*",0,start)
b1=master.find("/* ============================================================================",start+len(marker))
block=master[b0:b1 if b1>=0 else len(master)]

if ":where(.mv-ui-scope)" not in block:
    fail("action-menu block lacks mv-ui-scope")
if ".wlv-" not in block:
    fail("action-menu block lacks explicit WDV compatibility alias")
if ".mv-app .wlv-" in block:
    fail("action-menu block contains stale .mv-app WDV scope")

for selector in [
    ":where(.mv-ui-scope) .curve-header-action-menu,",
    ":where(.mv-ui-scope) .wlv-curve-header-action-menu",
    ":where(.mv-ui-scope) .curve-header-action-menu button,",
    ":where(.mv-ui-scope) .wlv-curve-header-action-menu button",
    ":where(.mv-ui-scope) .curve-header-action-menu button:hover:not(:disabled),",
    ":where(.mv-ui-scope) .curve-header-action-menu button:disabled,",
    ":where(.mv-ui-scope) .curve-menu-divider,",
    ":where(.mv-ui-scope) .wlv-curve-menu-divider",
]:
    if selector not in block:
        fail(f"missing action-menu master selector: {selector}")

local_geometry=[
    ".curve-header-action-menu {\n  position: absolute;",
    "top: calc(100% + 4px);",
    "right: 4px;",
    "z-index: 1000;",
    "min-width: 190px;",
    "padding: 6px;",
    ".curve-header-action-menu button {\n  display: block;",
    "width: 100%;",
    "min-height: 28px;",
    "padding: 7px 9px;",
    "text-align: left;",
    "font-size: 12px;",
    "cursor: pointer;",
    ".curve-header-action-menu button:disabled {\n  cursor: not-allowed;",
    ".curve-menu-divider {\n  height: 1px;",
    "margin: 5px 0;",
    ".curve-header-action-menu-portal {\n  position: fixed !important;",
    "z-index: 2147483000 !important;",
    "max-height: min(360px, calc(100vh - 16px));",
    "overflow-y: auto;",
    "pointer-events: auto;",
]
for needle in local_geometry:
    if needle not in track:
        fail(f"action-menu local geometry/interaction contract missing: {needle}")

for needle in [
    ".curve-header-action-menu button.danger {\n  color: #b42318;",
    ".curve-header-action-menu button.danger:hover {\n  background: #fff1f0;",
]:
    if needle not in track:
        fail(f"action-menu danger semantic contract missing: {needle}")

for needle in [
    ".wlv-track-placement-selector[data-combination-track-state='locked']",
    ".wlv-track-placement-selector[data-viewport-tied='true']",
    ".wlv-track-placement-selector[data-viewport-tie-role='leader']",
]:
    if needle not in track:
        fail(f"protected WDV Lock/Tie boundary missing: {needle}")

print("PASS WDV CURVE HEADER ACTION MENU PRESENTATION GUARD")
print("Curve-header action-menu neutral chrome: MASTER/PRESENT")
print("WDV compatibility aliases: MASTER/PRESENT")
print("Portal/menu geometry and interaction: LOCAL/PRESERVED")
print("Danger action semantics: LOCAL/PRESERVED")
print("WDV track-header / Lock-Tie boundary: LOCAL/PRESERVED")
