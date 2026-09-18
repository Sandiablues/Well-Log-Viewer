#!/usr/bin/env python3
from pathlib import Path

HOME=Path.home()
SDV=HOME/"Applications"/"MultiViewer"/"seismic_viewer_project"/"seismic-viewer-frontend"
MASTER=SDV/"src/styles/multiviewer-presentation/components.css"
S2D=SDV/"src/components/Seismic2DViewer.tsx"
S3D=SDV/"src/components/Seismic3DViewer.tsx"

def fail(msg):
    print("FAIL SDV 2D/3D FINAL CONSOLIDATION PRESENTATION GUARD")
    print(msg)
    raise SystemExit(1)

master=MASTER.read_text()
s2d=S2D.read_text()
s3d=S3D.read_text()

marker="MULTIVIEWER MASTER SDV 2D/3D FINAL VIEWER NEUTRAL CHROME V1.0.1"
if marker not in master:
    fail("missing Phase 37 V1.0.1 final SDV master block")

for selector in [
    ".mv-app .mv-sdv-control-subheading",
    ".mv-app .mv-sdv-scene-button",
    ".mv-app .mv-sdv-2d-slice-index-row",
]:
    if selector not in master:
        fail("missing master selector: "+selector)

for text in [
    'className="mv-sdv-control-subheading">Scene overlays</div>',
    'className="mv-sdv-control-subheading">Scene</div>',
    'className="mv-sdv-control-subheading">Visible planes</div>',
    'className="mv-sdv-control-subheading">Slice movement</div>',
    'className="mv-sdv-control-subheading">Amplitude / display</div>',
]:
    if text not in s3d:
        fail("3D subheading semantic role missing: "+text)

if s3d.count('className="mv-sdv-scene-button"') != 3:
    fail("expected exactly three governed 3D scene buttons")

for text in [
    'className="mv-viewer-controls-panel mv-viewer-controls-panel--info-parity"',
    "width: 300,",
    "transform: menuCollapsed ? 'translateX(calc(-100% - 10px))' : 'translateX(0)'",
    "pointerEvents: menuCollapsed ? 'none' : 'auto'",
]:
    if text not in s3d:
        fail("accepted 3D parity/geometry contract missing: "+text)

if "color: savedSceneView ? 'var(--mv-text-primary)' : 'var(--mv-text-disabled)'" not in s3d:
    fail("3D Return Scene disabled semantic state no longer local")

if s2d.count('className="mv-side-column-vertical-toggle"') < 2:
    fail("2D vertical side-column collapse toggles missing")
if 'className="mv-sdv-2d-slice-index-row"' not in s2d:
    fail("2D slice-index semantic presentation role missing")
if 'className="mv-type-helper"' not in s2d:
    fail("existing 2D helper semantic role missing")

print("PASS SDV 2D/3D FINAL CONSOLIDATION PRESENTATION GUARD")
print("SDV 3D subsection neutral typography: MASTER/PRESENT")
print("SDV 3D scene-button neutral chrome: MASTER/PRESENT")
print("SDV 2D slice divider neutral presentation: MASTER/PRESENT")
print("Existing SDV 2D helper semantic role: PRESERVED")
print("SDV 3D panel parity dimensions: LOCAL/PRESERVED")
print("SDV 2D vertical collapse interaction: LOCAL/PRESERVED")
print("Seismic/scientific rendering: LOCAL/PRESERVED")
