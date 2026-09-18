#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
tsx=(ROOT/"src/wells/wbv/Wellbore3DPage.tsx").read_text()
css=(ROOT/"src/wells/wbv/Wellbore3DPage.css").read_text()
def fail(x): raise SystemExit("FAIL WBV CORE/INTERVAL REGRESSION CONTRACT: "+x)
required=[
'WBV_CORE_RIGHT_PANEL_MUTUAL_EXCLUSION_RESTORE_V1_0_0_AUDITED',
'if (mode !== "none")',
'releaseCorePickingForRightPanel();',
'if (checked) releaseCorePickingForRightPanel();',
'requestSelectionMode("none");',
'wlv-wbv-interval-actions mv-control-geometry-scope-exempt',
'wlv-wbv-control-button--compact mv-control-geometry-exempt',
]
for x in required:
    if x not in tsx: fail("missing "+x)
if tsx.count("wlv-wbv-control-button--compact mv-control-geometry-exempt") != 2:
    fail("expected exactly 2 protected interval action buttons")
for x in [
'WBV INTERVAL ACTION PRESENTATION REGRESSION RESTORE V1.0.0',
'font-size: 0.64rem',
'min-height: 1.7rem',
'padding: 0.28rem 0.48rem',
'background: #101921',
]:
    if x not in css: fail("missing CSS contract "+x)
print("PASS WBV CORE/INTERVAL REGRESSION CONTRACT")
print("Core vs right-panel pointer ownership: MUTUALLY EXCLUSIVE")
print("Interval action geometry exemptions: 2/2")
print("Interval compact presentation: PRESENT")
