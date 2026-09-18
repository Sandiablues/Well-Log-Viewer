#!/usr/bin/env python3
from pathlib import Path

HOME=Path.home()
WLV=HOME/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
TSX=WLV/"src/wells/wdv/WdvPageBoundary.tsx"
TRACK=WLV/"src/styles/track-layout-prototype.css"
MASTER=WLV/"src/styles/multiviewer-presentation/components.css"

def fail(msg):
    raise SystemExit("FAIL WDV QUICK VIEW PRESENTATION GUARD: "+msg)

for p in (TSX,TRACK,MASTER):
    if not p.is_file():
        fail(f"missing {p}")

tsx=TSX.read_text()
track=TRACK.read_text()
master=MASTER.read_text()

# Master-owned Quick View presentation markers accumulated through Phases 12–18.
master_markers=[
    "MULTIVIEWER MASTER WDV QUICK VIEW METADATA CHROME V1.0.0",
    "MULTIVIEWER MASTER WDV QUICK VIEW STRUCTURED METADATA CHROME V1.0.0",
    "MULTIVIEWER MASTER WDV QUICK VIEW HEADER AND CURVE ROW SHELL V1.0.0",
    "MULTIVIEWER MASTER WDV QUICK VIEW COLLAPSE CONTROL CHROME V1.0.0",
    "MULTIVIEWER MASTER WDV QUICK VIEW COLLAPSED LABEL AND PANEL BODY V1.0.0",
    "MULTIVIEWER MASTER WDV QUICK VIEW TRANSIENT STATUS CHROME V1.0.0",
    "MULTIVIEWER MASTER WDV QUICK VIEW TECHNICAL DISCLOSURE TYPOGRAPHY V1.0.0",
]
for marker in master_markers:
    if marker not in master:
        fail("missing master marker "+marker)

required_master_selectors=[
    ":where(.mv-ui-scope) .wlv-qv-metadata-notice",
    ":where(.mv-ui-scope) .wlv-qv-source-name",
    ":where(.mv-ui-scope) .wlv-qv-qaqc-flag",
    ":where(.mv-ui-scope) .wlv-qv-technical-flags",
    ":where(.mv-ui-scope) .wlv-qv-metadata-card",
    ":where(.mv-ui-scope) .wlv-qv-metadata-label",
    ":where(.mv-ui-scope) .wlv-qv-metadata-value",
    ":where(.mv-ui-scope) .wlv-qv-summary-pill",
    ":where(.mv-ui-scope) .wlv-qv-shared-header-text",
    ":where(.mv-ui-scope) .wlv-qv-curve-row-compact",
    ":where(.mv-ui-scope) .wlv-curve-inventory-collapse-toggle",
    ":where(.mv-ui-scope) .wlv-curve-inventory-collapsed-label",
    ":where(.mv-ui-scope) .wlv-qv-metadata-panel",
    ":where(.mv-ui-scope) .wlv-qv-drop-overlay",
    ":where(.mv-ui-scope) .wlv-qv-status-message",
    ":where(.mv-ui-scope) .wlv-qv-technical-flags-summary",
    ":where(.mv-ui-scope) .wlv-qv-technical-flags-message",
]
for selector in required_master_selectors:
    if selector not in master:
        fail("missing master selector "+selector)

# Semantic/dynamic presentation must remain local.
tsx_required=[
    "function quickViewStatusTone(",
    "function quickViewToneColor(",
    "color: quickViewToneColor(tone)",
    "quickViewStatusTone(meta) === 'warning'",
    "wlv-qv-qaqc-${flag.severity}",
    "QUICK_VIEW_INVENTORY_COLORS",
    "<strong style={{ color }}>{curve.mnemonic}</strong>",
]
for needle in tsx_required:
    if needle not in tsx:
        fail("local semantic authority missing: "+needle)

# Geometry / interaction boundary must remain local.
tsx_geometry=[
    "gridTemplateColumns: '118px minmax(0, 1fr)'",
    "style={{ position: 'static', width: 28, height: 28, minWidth: 28, minHeight: 28",
    "style={{ padding: 8, overflowY: 'auto' }}",
    "style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 4 }}",
]
for needle in tsx_geometry:
    if needle not in tsx:
        fail("Quick View component geometry contract missing: "+needle)

track_geometry=[
    "grid-template-columns: 56px minmax(0, 1fr);",
    "transform: translateX(-50%) rotate(-90deg);",
    "z-index: 5000;",
    "pointer-events: none;",
    "max-width: min(680px, calc(100% - 32px));",
]
for needle in track_geometry:
    if needle not in track:
        fail("Quick View local CSS geometry contract missing: "+needle)

print("PASS WDV QUICK VIEW PRESENTATION GUARD")
print("Master-owned Quick View presentation blocks: 7/7")
print("Quick View semantic/dynamic colors: LOCAL/PRESERVED")
print("Quick View geometry/interaction boundary: LOCAL/PRESERVED")
