/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV curve overlay screen-space billboards", () => {
  it("adds html overlay bindings for curve labels and scales", () => {
    expect(renderer).toContain("type CurveHtmlLabelBinding = {");
    expect(renderer).toContain("type CurveHtmlScaleBinding = {");
    expect(renderer).toContain("syncHtmlOverlay(camera: THREE.Camera, viewportWidth: number, viewportHeight: number): void;");
  });

  it("creates DOM-based curve label and scale elements", () => {
    expect(renderer).toContain("function createCurveTextLabelElement(");
    expect(renderer).toContain("function createCurveScaleCanvasElement(curve: WbvCurveOverlayRenderCurve): HTMLDivElement");
    expect(renderer).toContain("labelOverlayRoot.appendChild(element);");
  });

  it("projects billboards into screen space on every frame", () => {
    expect(renderer).toContain("curveOverlayRuntime.syncHtmlOverlay(camera, viewportWidth, viewportHeight);");
    expect(renderer).toContain("contextCurveOverlayRuntimes.forEach((runtime) => runtime.syncHtmlOverlay(camera, viewportWidth, viewportHeight));");
  });

  it("preserves the immediate local interval-marker repair", () => {
    expect(renderer).toContain("let localIntervalStartProjection");
    expect(renderer).toContain("let pendingIntervalObserveCount = 0");
    expect(renderer).toContain("showImmediateIntervalProjection(projection)");
  });

  it("preserves sprite fallback", () => {
    expect(renderer).toContain("const sprite = createCurveScaleSprite(curve, curveWorldWidth);");
    expect(renderer).toContain("const sprite = createCurveTextLabelSprite(curve, labelPoint);");
  });
});
