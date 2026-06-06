#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
viewer = ROOT.parent / "seismic-viewer-frontend" / "src" / "components" / "Seismic3DViewer.tsx"
text = viewer.read_text(encoding="utf-8")

required = {
    "default slice detail 2x": "const [textureScale, setTextureScale] = useState(2);",
    "native preview while moving preserved": "const effectiveTextureScale = (fastPreviewWhileMoving && isSliceMoving) || isLivePreviewing ? 1 : textureScale;",
    "fast preview default preserved": "const [fastPreviewWhileMoving, setFastPreviewWhileMoving] = useState(true);",
    "slice detail label": "<label>Slice detail</label>",
    "reset slice detail": "setTextureScale(2)",
    "quality note": "Higher detail improves still-slice zoom quality. Movement preview stays native for responsiveness.",
    "linear min filter": "tex.minFilter = THREE.LinearFilter;",
    "linear mag filter": "tex.magFilter = THREE.LinearFilter;",
    "bilinear sampling": "sampleBilinear(sourceAxis0, sourceAxis1)",
    "texture stats type": "type SliceTextureStats = {",
    "texture stats state": "const [textureStats, setTextureStats]",
    "texture stats callback prop": "onTextureStats?: (axis: SliceAxis, stats: SliceTextureStats) => void;",
    "texture stats callback handler": "const handleTextureStats = useCallback",
    "texture stats render timing": "textureRenderStartedAt",
    "texture width diagnostic": "Texture size",
    "source slice diagnostic": "Source slice",
    "texture render diagnostic": "Texture render",
    "active detail diagnostic": "activeTextureDetailMode",
}

missing = [name for name, needle in required.items() if needle not in text]
if missing:
    raise SystemExit("FAIL 3D slice detail static contract missing: " + ", ".join(missing))

if "const [textureScale, setTextureScale] = useState(1);" in text:
    raise SystemExit("FAIL 3D slice detail static contract: stale Native default remains")

print("PASS 3D slice detail static contract")
