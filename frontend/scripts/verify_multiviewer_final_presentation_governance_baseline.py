#!/usr/bin/env python3
from pathlib import Path
import hashlib
HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
FILES={
"WLV/src/wells/wdv/WdvPageBoundary.tsx":WLV/"src/wells/wdv/WdvPageBoundary.tsx",
"WLV/src/styles/track-layout-prototype.css":WLV/"src/styles/track-layout-prototype.css",
"WLV/src/wells/wbv/Wellbore3DPage.css":WLV/"src/wells/wbv/Wellbore3DPage.css",
"WLV/src/styles/multiviewer-presentation/components.css":WLV/"src/styles/multiviewer-presentation/components.css",
"SDV/src/components/Seismic2DViewer.tsx":SDV/"src/components/Seismic2DViewer.tsx",
"SDV/src/components/Seismic3DViewer.tsx":SDV/"src/components/Seismic3DViewer.tsx",
"SDV/src/styles/multiviewer-presentation/components.css":SDV/"src/styles/multiviewer-presentation/components.css",
}
EXPECTED={'WLV/src/wells/wdv/WdvPageBoundary.tsx': '0f3ac5a3eb13ed44680fc1765461001457bf8f95d895d8dc17b2c575143a6fcf', 'WLV/src/styles/track-layout-prototype.css': 'ab1a282a2acbd64f84de1743286865f9bc46ec4daab0c2d2fd2268b68c522c11', 'WLV/src/wells/wbv/Wellbore3DPage.css': '05e52083977f4867bdf3f4c57b4001e2bca2a5829b1a634bfeb78d9f370631a6', 'WLV/src/styles/multiviewer-presentation/components.css': 'f3368cad3f6d03a9bef9fa665e6c9348b03641d2659be0713c075f25aa5e8cfa', 'SDV/src/components/Seismic2DViewer.tsx': 'aa993cb960ab3fb5453130feb4ca34b1a0cedd5a6ee4e0be36608597f1333fd2', 'SDV/src/components/Seismic3DViewer.tsx': '84c5fe7926c98826f401785729ceced2efe3c4b939f41d0365481a9b2a73b0c1', 'SDV/src/styles/multiviewer-presentation/components.css': 'f3368cad3f6d03a9bef9fa665e6c9348b03641d2659be0713c075f25aa5e8cfa'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):
    print("FAIL MULTIVIEWER FINAL PRESENTATION GOVERNANCE BASELINE GUARD")
    print(m); raise SystemExit(1)
for key,p in FILES.items():
    if not p.is_file(): fail("missing baseline file: "+key)
    live=sha(p)
    if live!=EXPECTED[key]: fail(f"baseline SHA drift: {key} {live}")
if FILES["WLV/src/styles/multiviewer-presentation/components.css"].read_bytes()!=FILES["SDV/src/styles/multiviewer-presentation/components.css"].read_bytes():
    fail("shared master identity mismatch")
print("PASS MULTIVIEWER FINAL PRESENTATION GOVERNANCE BASELINE GUARD")
print("WDV governed presentation baseline: LOCKED")
print("WBV/WLV governed presentation baseline: LOCKED")
print("SDV 2D/3D governed presentation baseline: LOCKED")
print("Shared presentation master identity: EXACT")
print("Final baseline files checked: 7")
