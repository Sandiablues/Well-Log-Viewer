/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV curve camera-facing + anchored exact-current V1.0.2", () => {
  it("declares world-to-local camera basis inside addCurveOverlays update()", () => {
    const fnStart = renderer.indexOf("function addCurveOverlays(");
    const fnEnd = renderer.indexOf("\\nfunction materialList(", fnStart);
    const fn = renderer.slice(fnStart, fnEnd);
    const updateStart = fn.indexOf("const update = (camera: THREE.Camera) => {");
    const syncStart = fn.indexOf("const syncHtmlOverlay =", updateStart);
    const update = fn.slice(updateStart, syncStart);
    expect(update).toContain("const worldToLocalQuaternion = groupWorldQuaternion.clone().invert();");
    expect(update.match(/worldToLocalQuaternion/g)?.length).toBe(4);
  });

  it("refreshes curve geometry on model rotation", () => {
    expect(renderer).toContain("const modelOrientationChanged");
    expect(renderer).toContain("if (cameraOrientationChanged || modelOrientationChanged)");
  });

  it("anchors labels/scales through current matrixWorld", () => {
    expect(renderer).toContain("point.applyMatrix4(group.matrixWorld).project(camera)");
    expect(renderer).toContain("innerWorld.applyMatrix4(group.matrixWorld).project(camera)");
    expect(renderer).toContain("outerWorld.applyMatrix4(group.matrixWorld).project(camera)");
  });

  it("sizes scale from actual projected track span", () => {
    expect(renderer).toContain("Math.hypot(outerX - innerX, outerY - innerY)");
  });

  it("preserves local rapid-pick marker behavior", () => {
    expect(renderer).toContain("let localIntervalStartProjection");
    expect(renderer).toContain("showImmediateIntervalProjection(projection)");
  });
});
