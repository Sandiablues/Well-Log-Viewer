#!/usr/bin/env python3
from pathlib import Path
import hashlib
HOME=Path.home()
F=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
P=F/"src/wells/wbv/Wellbore3DPage.css"
EXPECTED="05e52083977f4867bdf3f4c57b4001e2bca2a5829b1a634bfeb78d9f370631a6"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL WBV RIGHT-PANEL MASTER TYPOGRAPHY OWNERSHIP GUARD")
    print(m); raise SystemExit(1)
if sha(P)!=EXPECTED: fail("WBV CSS drift")
t=P.read_text()
for forbidden in [
    "font-weight: var(--mv-font-weight-semibold);",
]:
    # This declaration may exist elsewhere legitimately; reject only the old exact right-panel block signature.
    pass
if """.wlv-wbv-panel--right .wlv-wbv-well-summary__row > span,
.wlv-wbv-panel--right .wlv-wbv-trajectory-list__row > span,
.wlv-wbv-panel--right .wlv-wbv-selected-point-label {
  color: var(--mv-text-secondary);
  font-weight: var(--mv-font-weight-semibold);
}""" in t:
    fail("legacy right-panel semibold label ownership returned")
if """.wlv-wbv-panel--right .wlv-wbv-panel-heading > strong {
  margin-bottom: 0.24rem;
  font-size: 0.86rem;
  line-height: 1.22;
}""" in t:
    fail("legacy right-panel title sizing returned")
required=[
  "Typography for normalized right-panel property roles is owned by the",
  "Right panel title typography is master-owned through mv-role-panel-title.",
  "font-size: var(--mv-font-size-xs);",
  "font-weight: var(--mv-font-weight-normal);",
]
for x in required:
    if x not in t: fail("missing ownership contract: "+x)
print("PASS WBV RIGHT-PANEL MASTER TYPOGRAPHY OWNERSHIP GUARD")
print("Legacy semibold label ownership: REMOVED")
print("Legacy right-panel title sizing: REMOVED")
print("Active-well helper: 11/400/MUTED")
print("WBV right-panel geometry: PRESERVED")
