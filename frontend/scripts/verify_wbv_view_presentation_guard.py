#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
TSX=ROOT/"src/wells/wbv/Wellbore3DPage.tsx"
CSS=ROOT/"src/wells/wbv/Wellbore3DPage.css"
MIG=ROOT/"src/styles/multiviewer-presentation/migration-stage1-neutral-controls.css"
MASTER=ROOT/"src/styles/multiviewer-presentation/components.css"

def fail(msg):
    raise SystemExit("FAIL WBV VIEW PRESENTATION GUARD: "+msg)

for p in (TSX,CSS,MIG,MASTER):
    if not p.is_file(): fail(f"missing {p}")

tsx=TSX.read_text()
css=CSS.read_text()
mig=MIG.read_text()
master=MASTER.read_text()

m=re.search(r'<section className="([^"]*\bwlv-wbv-view-controls\b[^"]*)" aria-label="WBV view controls">(.*?)</section>',tsx,re.S)
if not m: fail("WBV View controls section not found")
classes=set(m.group(1).split())
body=m.group(2)

if "mv-control-geometry-scope-exempt" not in classes:
    fail("View section lost mv-control-geometry-scope-exempt")

buttons=re.findall(r'<button\b[^>]*>',body)
if len(buttons)!=13:
    fail(f"expected 13 View buttons, found {len(buttons)}")
missing=[i+1 for i,b in enumerate(buttons) if "mv-control-geometry-exempt" not in b]
if missing:
    fail(f"View buttons missing mv-control-geometry-exempt: {missing}")

scope_count=mig.count(":not(.mv-control-geometry-scope-exempt *)")
if scope_count < 8:
    fail(f"legacy migration scope exclusion incomplete: {scope_count}")

combined=css+"\n"+master
for needle in [
    "font-size: 0.68rem",
    "font-size: 0.58rem",
    "min-height: 1.72rem",
    "font-size: 0.62rem",
    "border-radius: 999px",
]:
    if needle not in combined:
        fail("accepted compact View contract missing: "+needle)

print("PASS WBV VIEW PRESENTATION GUARD")
print("View section scope exemption: PRESENT")
print("View button individual exemptions: 13/13")
print(f"Legacy migration scope exclusions: {scope_count}")
print("Accepted compact View contract: PRESENT")
