from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    viewer = root / "seismic-viewer-frontend" / "src" / "components" / "Seismic2DViewer.tsx"
    service = root / "seismic-viewer-frontend" / "src" / "services" / "zarrService.ts"
    backend_service = root / "seismic-viewer-backend" / "app" / "services" / "sections2d_service.py"

    viewer_text = viewer.read_text(encoding="utf-8")
    service_text = service.read_text(encoding="utf-8")
    backend_service_text = backend_service.read_text(encoding="utf-8")

    require("fetchSection2DWindow" in viewer_text, "Seismic2DViewer must consume fetchSection2DWindow")
    require("/api/section2d/window" in service_text, "zarrService must expose /api/section2d/window")
    require("SourceWindow2D" in viewer_text, "Seismic2DViewer must track source-window state")
    require("setSourceWindow" in viewer_text, "Seismic2DViewer must update source-window state on zoom/reset")
    require("imageRendering: 'pixelated'" not in viewer_text, "2D canvas must not force pixelated scaling")
    require("imageRendering: 'auto'" in viewer_text, "2D canvas should use normal browser interpolation")
    require("renderRequestSeqRef" in viewer_text, "2D renderer must guard against stale async renders")
    require("WINDOW_RENDER_MAX_WIDTH" in viewer_text, "2D renderer must cap window render width")
    require("WINDOW_RENDER_MAX_HEIGHT" in viewer_text, "2D renderer must cap window render height")
    require("requestElapsedMs" in viewer_text, "2D renderer must expose client request timing")
    require("backendRenderMs" in viewer_text, "2D renderer must expose backend render timing")
    require("sourceWindowPixelCount" in viewer_text, "2D renderer must track source window pixel count")
    require("outputPixelCount" in viewer_text, "2D renderer must track output pixel count")
    require("formatRenderMs" in viewer_text, "2D renderer must format render timings for UI diagnostics")
    require("render_time_ms" in backend_service_text, "2D backend section service must return render_time_ms")
    require(backend_service_text.count("render_started_at = time.perf_counter()") >= 2, "Both preview and window render paths must initialize render_started_at")
    require("output_pixel_count" in backend_service_text, "2D backend section service must return output_pixel_count")

    require("PanDrag2D" in viewer_text, "2D renderer must define pan drag state for zoom-window navigation")
    require("shiftWindowRange" in viewer_text, "2D renderer must clamp pan shifts to source bounds")
    require("setPanDrag" in viewer_text, "2D renderer must track pan drag state")
    require("drag to pan" in viewer_text, "2D renderer must expose pan guidance when zoomed")
    require("cursor: boxZoomEnabled ? 'crosshair' : sourceWindow ?" in viewer_text, "2D renderer must switch cursor for zoom-window panning")
    require("setBoxZoomEnabled(false)" in viewer_text, "2D box zoom must automatically leave box-zoom mode after a successful zoom so drag-to-pan works immediately")

    print("PASS 2D render quality static contract")


if __name__ == "__main__":
    main()
