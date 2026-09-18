#!/usr/bin/env python3
from pathlib import Path
import hashlib

HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"

FILES={
    "WLV_MAIN": WLV/"src/main.tsx",
    "SDV_MAIN": SDV/"src/main.tsx",
    "WLV_RUNTIME": WLV/"src/themeRuntime.tsx",
    "SDV_RUNTIME": SDV/"src/themeRuntime.tsx",
    "WLV_THEME": WLV/"src/styles/multiviewer-presentation/theme.css",
    "SDV_THEME": SDV/"src/styles/multiviewer-presentation/theme.css",
}
EXPECTED={
    "WLV_MAIN": 'ce34c54d56dc10e590c42baf13bdd969083fb7e7501e79f7a567dff576fd4386',
    "SDV_MAIN": '55980ef4ada9af584c3679cba1b0011f9f67018637509fc01f5d8234bf1c65bc',
    "WLV_RUNTIME": 'ca415a94df2ebb9b69a6d3085bbfcdbb8141a684616693752de34687bac6e446',
    "SDV_RUNTIME": 'ca415a94df2ebb9b69a6d3085bbfcdbb8141a684616693752de34687bac6e446',
    "WLV_THEME": '42948d0b0f6dffd2405f53889272f202ac2b0a7c4f55faf79f2a4575b8ce8b54',
    "SDV_THEME": '42948d0b0f6dffd2405f53889272f202ac2b0a7c4f55faf79f2a4575b8ce8b54',
}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL MULTIVIEWER GLOBAL THEME SWITCH GUARD")
    print(m)
    raise SystemExit(1)

for key,p in FILES.items():
    if not p.is_file():
        fail("missing Phase40 file: "+key)
    if sha(p)!=EXPECTED[key]:
        fail("Phase40 SHA drift: "+key)

if FILES["WLV_RUNTIME"].read_bytes()!=FILES["SDV_RUNTIME"].read_bytes():
    fail("WLV/SDV theme runtime identity mismatch")
if FILES["WLV_THEME"].read_bytes()!=FILES["SDV_THEME"].read_bytes():
    fail("WLV/SDV shared theme identity mismatch")

runtime=FILES["WLV_RUNTIME"].read_text()
for required in [
    "import { useEffect, useState } from 'react';",
    "multiviewer:theme",
    "multiviewer_theme",
    "document.documentElement.dataset.mvTheme = theme",
    "window.localStorage.setItem(STORAGE_KEY, theme)",
    "document.cookie =",
    "window.setInterval(syncFromPersistence, 1000)",
    'className="mv-theme-toggle"',
]:
    if required not in runtime:
        fail("theme runtime contract missing: "+required)

if "import React," in runtime:
    fail("unused default React import reintroduced")

for main in [FILES["WLV_MAIN"].read_text(),FILES["SDV_MAIN"].read_text()]:
    if "installMultiViewerThemeRuntime" not in main:
        fail("theme bootstrap missing from main")
    if "<ThemeToggle />" not in main:
        fail("global ThemeToggle missing from main")

print("PASS MULTIVIEWER GLOBAL THEME SWITCH GUARD")
print("WLV/SDV theme runtime identity: EXACT")
print("Unused default React import: ABSENT")
print("Root data-mv-theme bootstrap: PRESENT")
print("Persistent Dark/Light control: PRESENT")
print("Cross-port same-host cookie synchronization: PRESENT")
print("Dark default: PRESERVED")
