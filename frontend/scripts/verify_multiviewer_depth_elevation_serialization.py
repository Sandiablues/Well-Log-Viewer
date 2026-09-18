#!/usr/bin/env python3
from pathlib import Path
import hashlib
HOME=Path.home(); WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"; SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
WT=WLV/"src/styles/multiviewer-presentation/theme.css"; ST=SDV/"src/styles/multiviewer-presentation/theme.css"; EXPECTED="7c9a8ee1185fda6a32a854d20f3fdb4606a5d4c22be53b27b431f0497c976a69"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m): print("FAIL MULTIVIEWER DEPTH/ELEVATION SERIALIZATION GUARD"); print(m); raise SystemExit(1)
for p in [WT,ST]:
    if not p.is_file() or sha(p)!=EXPECTED: fail("theme.css drift: "+str(p))
if WT.read_bytes()!=ST.read_bytes(): fail("shared theme identity mismatch")
text=WT.read_text(); idx=text.find("MULTIVIEWER LIGHT THEME DEPTH & ELEVATION ROLES V1.0.0")
if idx<0: fail("Phase40.6 marker missing")
section=text[idx-120:]
if "\\n" in section: fail("literal escaped newline corruption present in Phase40.6 CSS")
for token in ["--mv-depth-page:","--mv-depth-panel:","--mv-depth-panel-header:","--mv-depth-raised:","--mv-depth-control:","--mv-depth-shadow-1:","--mv-depth-shadow-2:"]:
    if token not in section: fail("depth token missing: "+token)
print("PASS MULTIVIEWER DEPTH/ELEVATION SERIALIZATION GUARD")
print("Phase40.6 CSS escaped-newline corruption: ABSENT")
print("Depth/elevation roles: PRESENT")
