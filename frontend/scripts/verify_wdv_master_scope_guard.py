#!/usr/bin/env python3
from pathlib import Path
import re

HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
MASTER=WLV/"src/styles/multiviewer-presentation/components.css"
TRACK=WLV/"src/styles/track-layout-prototype.css"
MAIN=WLV/"src/main.tsx"

def fail(msg):
    raise SystemExit("FAIL WDV MASTER SCOPE GUARD: "+msg)

for p in (MASTER,TRACK,MAIN):
    if not p.is_file():
        fail(f"missing {p}")

main=MAIN.read_text()
master=MASTER.read_text()
track=TRACK.read_text()

if 'document.documentElement.classList.add("mv-ui-scope")' not in main:
    fail("WLV no longer declares mv-ui-scope")
if 'classList.add("mv-app")' in main:
    fail("unexpected WLV mv-app root; review scope contract")

# Every governed WDV block in the shared master is scope-protected.
# This intentionally discovers future WDV master blocks automatically instead
# of maintaining a brittle Phase-8/9/10-only marker list.
matches=list(re.finditer(r"MULTIVIEWER MASTER WDV[^\\n*]*", master))
if len(matches) < 11:
    fail(f"expected at least 11 governed WDV master blocks, found {len(matches)}")

checked=[]
for idx,m in enumerate(matches):
    marker=m.group(0).strip()
    start=master.rfind("/*",0,m.start())
    if start < 0:
        fail("cannot resolve block start: "+marker)
    next_i=master.find("/* ==========================================================================",m.end())
    end=len(master) if next_i < 0 else next_i
    block=master[start:end]

    if ".wlv-" not in block:
        fail("WDV master block contains no WLV selector: "+marker)
    if ":where(.mv-ui-scope)" not in block:
        fail("WDV master block does not target mv-ui-scope: "+marker)
    if ".mv-app .wlv-" in block:
        fail("stale mv-app WDV selector remains: "+marker)
    checked.append(marker)

if "WDV MENU / TOOLBAR PRESENTATION REGRESSION RESTORE V1.0.0" not in track:
    fail("local WDV fallback marker missing")
if ":where(.mv-ui-scope) .wlv-toolbar-group" not in track:
    fail("local WDV toolbar fallback has wrong scope")

print("PASS WDV MASTER SCOPE GUARD")
print("WLV root authority: mv-ui-scope")
print(f"Governed WDV master blocks checked: {len(checked)}")
print("All governed WDV master selectors: MATCH WLV")
print("Local WDV menu fallback selectors: MATCH WLV")
