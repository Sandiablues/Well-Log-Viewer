/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV interval AOI controls", () => {
  it("uses backend interaction endpoints and explicit Log Viewer AOI command", () => {
    expect(page).toContain("interaction/interval/send-to-wdv");
    expect(page).toContain("Send to Log Viewer as AOI");
    expect(page).toContain('selection_mode === "point"');
    expect(page).toContain('selection_mode === "interval"');
  });

  it("picks against the continuous projected trajectory rather than sparse survey points", () => {
    expect(renderer).toContain("nearestSegmentOnScreen(event");
    expect(renderer).toContain("nearest.distance > 20");
    expect(renderer).toContain("interpolateRenderPoint(firstPoint, secondPoint, nearest.ratio)");
    expect(renderer).not.toContain("raycaster.intersectObject(pickPoints");
  });

  it("uses red always-front bullseye sprites and bounded inverse zoom scaling", () => {
    expect(renderer).toContain("new THREE.SpriteMaterial");
    expect(renderer).toContain("const marker = new THREE.Sprite(material)");
    expect(renderer).toContain("#e23232");
    expect(renderer).toContain("marker.renderOrder = 200");
    expect(renderer).toContain("markerScaleForZoom(camera.zoom)");
    expect(renderer).toContain("THREE.MathUtils.clamp(Math.pow(safeZoom, -1.35), 0.18, 1.6)");
    expect(renderer).not.toContain("new THREE.RingGeometry");
  });
});
