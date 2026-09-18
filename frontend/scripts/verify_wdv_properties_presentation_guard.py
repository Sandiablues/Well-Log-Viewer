#!/usr/bin/env python3
from pathlib import Path

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"
TRACK=ROOT/"src/styles/track-layout-prototype.css"

def fail(msg):
    print("FAIL WDV PROPERTIES PRESENTATION GUARD")
    print(msg)
    raise SystemExit(1)

master=MASTER.read_text()
track=TRACK.read_text()

markers=[
    "MULTIVIEWER MASTER WDV TOOLBAR / PROPERTIES CHROME V1.0.0",
    "MULTIVIEWER MASTER WDV PROPERTIES PANEL SHELL / HEADER CHROME V1.0.0",
    "MULTIVIEWER MASTER WDV PROPERTIES METADATA TYPOGRAPHY / DIVIDERS V1.0.0",
    "MULTIVIEWER MASTER WDV PROPERTIES NOTE / SELECTED CURVE NEUTRAL CHROME V1.0.0",
]
for marker in markers:
    if marker not in master:
        fail(f"missing master marker: {marker}")

for marker in markers[1:]:
    start=master.find(marker)
    b0=master.rfind("/*",0,start)
    b1=master.find("/* ==========================================================================",start+len(marker))
    block=master[b0:b1 if b1>=0 else len(master)]
    if ":where(.mv-ui-scope)" not in block:
        fail(f"master block lacks mv-ui-scope: {marker}")
    if ".mv-app .wlv-" in block:
        fail(f"forbidden .mv-app WDV scope: {marker}")

local_geometry=[
    ".wlv-properties-panel-v2 .wlv-properties-selected-entity {\n  margin: 10px;",
    "padding: 9px 10px;",
    "display: grid;",
    "gap: 3px;",
    ".wlv-properties-panel-v2 .wlv-properties-tabs {\n  display: grid;",
    "grid-template-columns: 1fr 1fr;",
    "margin: 0 10px 10px;",
    ".wlv-properties-panel-v2 .wlv-properties-tabs button {\n  min-height: 32px;",
    ".wlv-properties-panel-v2 .wlv-properties-tab-body {\n  overflow: auto;",
    ".wlv-properties-panel-v2 .wlv-properties-contract-table {\n  margin: 0 10px 10px;",
    "overflow: hidden;",
    ".wlv-properties-panel-v2 .wlv-properties-contract-section table {\n  width: 100%;",
    "table-layout: fixed;",
    "padding: 7px 9px;",
    "width: 38%;",
    "word-break: break-word;",
    ".wlv-properties-panel-v2 .wlv-properties-dark-section,\n.wlv-properties-panel-v2 .wlv-property-section {\n  margin: 10px;",
]
for needle in local_geometry:
    if needle not in track:
        fail(f"local geometry/wrapping contract missing: {needle}")

local_semantics=[
    ".wlv-properties-panel-v2 .wlv-properties-tabs button.active {",
    "box-shadow: inset 0 -2px 0 #9ca3af;",
    ".wlv-properties-panel-v2 .wlv-property-section button:disabled {",
    "opacity: 0.75;",
]
for needle in local_semantics:
    if needle not in track:
        fail(f"local semantic-state contract missing: {needle}")

for forbidden in [
    ".wlv-properties-panel-v2 {\n  background: #0f0f10;",
    ".wlv-properties-panel-v2 .wlv-panel-heading {\n  border-bottom: 1px solid #3f3f46;",
    ".wlv-properties-panel-v2 .wlv-properties-selected-entity span {\n  color: #a1a1aa;",
    ".wlv-properties-panel-v2 .wlv-property-note {\n  border-color: #4b5563;",
    ".wlv-properties-panel-v2 .wlv-selected-curve-title {\n  border-color: #4b5563;",
]:
    if forbidden in track:
        fail(f"duplicate local neutral authority reintroduced: {forbidden}")

print("PASS WDV PROPERTIES PRESENTATION GUARD")
print("Master-owned Properties presentation blocks: 4/4")
print("Properties shell/metadata/note neutral presentation: MASTER/PRESENT")
print("Properties geometry/wrapping: LOCAL/PRESERVED")
print("Properties active/disabled semantic states: LOCAL/PRESERVED")
