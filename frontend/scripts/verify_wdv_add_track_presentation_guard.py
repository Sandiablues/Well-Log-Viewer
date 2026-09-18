#!/usr/bin/env python3
from pathlib import Path

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"
TRACK=ROOT/"src/styles/track-layout-prototype.css"

def fail(msg):
    print("FAIL WDV ADD TRACK PRESENTATION GUARD")
    print(msg)
    raise SystemExit(1)

master=MASTER.read_text()
track=TRACK.read_text()

marker="MULTIVIEWER MASTER WDV ADD TRACK BUILDER SHELL / LABEL CHROME V1.0.0"
if marker not in master:
    fail("missing Phase 31 Add Track master marker")

start=master.find(marker)
b0=master.rfind("/*",0,start)
b1=master.find("/* ==========================================================================",start+len(marker))
block=master[b0:b1 if b1>=0 else len(master)]

if ":where(.mv-ui-scope)" not in block:
    fail("Phase 31 Add Track block lacks mv-ui-scope")
if ".mv-app .wlv-" in block:
    fail("Phase 31 Add Track block contains forbidden .mv-app WDV scope")

for selector in [
    ":where(.mv-ui-scope) .wlv-add-track-builder,",
    ":where(.mv-ui-scope) .wlv-add-track-builder-draggable",
    ":where(.mv-ui-scope) .wlv-add-track-builder-draggable .builder-drag-handle",
    ":where(.mv-ui-scope) .wlv-add-track-builder .builder-label",
    ":where(.mv-ui-scope) .wlv-add-track-builder .builder-note",
]:
    if selector not in block:
        fail(f"missing Add Track master selector: {selector}")

# Local geometry/type-size ownership established by Phase31.
local_geometry=[
    ".wlv-add-track-builder {\n  width: 380px;",
    "max-width: calc(100vw - 24px);",
    "max-height: calc(100vh - 24px);",
    "padding: 10px;",
    "overflow: auto;",
    "border-radius: 6px;",
    ".wlv-add-track-builder-floating {\n  position: fixed;",
    ".builder-heading,\n.builder-actions {\n  display: flex;",
    ".builder-section {\n  margin-top: 10px;",
    ".builder-label {\n  margin-bottom: 5px;",
    "font-size: 11px;",
    "font-weight: 900;",
    "text-transform: uppercase;",
    ".builder-note {\n  margin: 6px 0 0;",
    "line-height: 1.35;",
]
for needle in local_geometry:
    if needle not in track:
        fail(f"Add Track local geometry/type contract missing: {needle}")

# Semantic and behavioral states must stay local.
local_semantics=[
    ".wlv-add-track-builder button.active,\n.wlv-add-track-builder .builder-primary {",
    "border-color: #20c97a;",
    "background: rgba(16, 185, 129, 0.18);",
    "color: #5df0aa;",
    ".wlv-add-track-builder button:disabled {",
    "border-color: #333842;",
    "background: #1b1e23;",
    "color: #646b75;",
    "opacity: 1;",
    ".wlv-add-track-button {",
    ".wlv-add-track-button:hover:not(:disabled)",
]
for needle in local_semantics:
    if needle not in track:
        fail(f"Add Track semantic/behavior contract missing: {needle}")

# Prevent duplicate local neutral authority from returning.
for forbidden in [
    ".wlv-add-track-builder,\n.wlv-add-track-builder-draggable {\n  border-color: #4b5563;",
    ".wlv-add-track-builder-draggable .builder-drag-handle {\n  border-bottom-color: #3f4650;",
    ".wlv-add-track-builder .builder-label {\n  color: #aeb7c3;",
    ".wlv-add-track-builder .builder-note {\n  color: #8d96a3;",
]:
    if forbidden in track:
        fail(f"duplicate Add Track neutral authority reintroduced: {forbidden}")

# Critical boundary carried forward from Phase30.
for needle in [
    ".wlv-track-placement-selector[data-combination-track-state='locked']",
    ".wlv-track-placement-selector[data-viewport-tied='true']",
    ".wlv-track-placement-selector[data-viewport-tie-role='leader']",
]:
    if needle not in track:
        fail(f"protected WDV Lock/Tie boundary missing: {needle}")

print("PASS WDV ADD TRACK PRESENTATION GUARD")
print("Add Track neutral shell/handle/label/note presentation: MASTER/PRESENT")
print("Add Track geometry/type sizing: LOCAL/PRESERVED")
print("Add Track active/disabled/green semantics: LOCAL/PRESERVED")
print("WDV track-header / Lock-Tie boundary: LOCAL/PRESERVED")
