from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
DESIGN = PROJECT / "docs" / "rendering" / "3D_ACTIVE_SLICE_VIEWPORT_WINDOW_DESIGN.md"
MODEL = PROJECT / "seismic-viewer-frontend" / "src" / "rendering3d" / "activeSliceRequestModel.ts"
VIEWER = PROJECT / "seismic-viewer-frontend" / "src" / "components" / "Seismic3DViewer.tsx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")
    viewer = VIEWER.read_text(encoding="utf-8")

    for phrase in [
        "MSI representation identity",
        "physical volume resolution",
        "active-slice viewport-window rendering",
        "GET /api/msi/representations/{representation_id}/slice-window",
        "while moving camera or slice",
        "Cache Key",
        "3D-C3 — One-Plane Prototype",
        "3D-C2 — Active Bounds Diagnostics",
    ]:
        require(phrase in design, f"missing design phrase: {phrase}")

    for phrase in [
        "Active3DSliceWindowRequest",
        "ACTIVE_3D_AXIS_MAPPING",
        "inline",
        "crossline",
        "time",
        "buildActive3DSliceWindowCacheKey",
        "buildActive3DSliceWindowQuery",
        "buildWholeSliceSourceBoundsForAxis",
        "getActive3DSliceIndex",
        "formatActive3DSourceBounds",
        "representationId",
    ]:
        require(phrase in model, f"missing model phrase: {phrase}")

    for phrase in [
        "activeDiagnosticAxis",
        "buildWholeSliceSourceBoundsForAxis",
        "formatActive3DSourceBounds",
        "whole-slice baseline",
        "Future cache key",
    ]:
        require(phrase in viewer, f"missing viewer diagnostic phrase: {phrase}")

    require("/api/volumes" not in model, "request model must not prefer legacy /api/volumes routes")
    require("physicalVolumeId" not in model, "request model must not expose physical volume ID as frontend authority")

    print("PASS 3D active-slice design static contract")


if __name__ == "__main__":
    main()
