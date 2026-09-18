#!/usr/bin/env python3
from pathlib import Path
import hashlib
HOME=Path.home()
F=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
WDV=F/'src/wells/prototype/WellLogPropertiesPanelSlot.tsx'; WBV=F/'src/wells/wbv/Wellbore3DPage.tsx'
WDV_SHA="7b37c8037b51bdd4a10278e20f14d5db76b444b7d8ed9fae722f07cf2e4ae373"; WBV_SHA="c9b20820380edad4aa41979427fa4ec1fdbe83aa8c295aaa37da7d3f7ab1369d"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL RIGHT-PANEL ROLE NORMALIZATION GUARD"); print(m); raise SystemExit(1)
if sha(WDV)!=WDV_SHA: fail("WDV component drift")
if sha(WBV)!=WBV_SHA: fail("WBV component drift")
w=WDV.read_text(); b=WBV.read_text()

wdv_roles=['mv-viewer-info-card', 'mv-role-panel-shell', 'mv-role-panel-title', 'mv-role-section-shell', 'mv-role-section-title', 'mv-role-property-grid', 'mv-role-property-row', 'mv-role-property-label', 'mv-role-property-value', 'mv-role-action-button', 'mv-role-collapse-control', 'mv-type-section-heading', 'mv-type-property-label', 'mv-type-property-value']
wbv_roles=['mv-viewer-info-card', 'mv-role-panel-shell', 'mv-role-panel-title', 'mv-role-section-shell', 'mv-role-section-title', 'mv-role-property-row', 'mv-role-property-label', 'mv-role-property-value', 'mv-role-helper-text', 'mv-role-collapse-control', 'mv-type-section-heading', 'mv-type-property-label', 'mv-type-property-value']
for role in wdv_roles:
    if role not in w: fail("WDV missing role: "+role)
for role in wbv_roles:
    if role not in b: fail("WBV missing role: "+role)

if w.count('className="mv-role-property-row"') < 3:
    fail("WDV property rows not comprehensively mapped")
if b.count("mv-role-property-row") < 12:
    fail("WBV property rows not comprehensively mapped")

print("PASS RIGHT-PANEL ROLE NORMALIZATION GUARD")
print("SDV canonical semantic classes: CONSUMED BY WDV/WBV")
print("WDV panel/title/section/row/label/value/actions: NORMALIZED")
print("WBV panel/title/section/row/label/value/helper: NORMALIZED")
print("CSS value parity: NOT YET CLAIMED")
