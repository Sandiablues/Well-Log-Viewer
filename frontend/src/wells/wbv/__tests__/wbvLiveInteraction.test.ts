import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  cameraFacingMarkerPosition,
  interpolateCurveValueAtMd,
  markerScaleForZoom,
  nearestSegmentOnScreen,
} from "../WellboreTrajectoryRenderer";

describe("WBV live interaction geometry", () => {
  it("resolves a click against the continuous projected trajectory, not survey points only", () => {
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    camera.position.set(0, 0, 2);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    const canvas = { getBoundingClientRect: () => ({ left: 10, top: 20, width: 200, height: 200 }) } as unknown as HTMLCanvasElement;
    const event = { clientX: 110, clientY: 120 } as PointerEvent;
    const result = nearestSegmentOnScreen(event, canvas, camera, [new THREE.Vector3(-0.8, 0, 0), new THREE.Vector3(0.8, 0, 0)]);
    expect(result?.segmentIndex).toBe(0);
    expect(result?.ratio).toBeCloseTo(0.5, 5);
    expect(result?.distance).toBeCloseTo(0, 5);
  });

  it("offsets a marker toward the camera", () => {
    const base = new THREE.Vector3(1, 2, 3);
    const positioned = cameraFacingMarkerPosition(base, new THREE.Vector3(0, 0, -1), 0.06);
    expect(positioned.z).toBeCloseTo(3.06, 8);
    expect(base.z).toBe(3);
  });

  it("makes the bullseye progressively smaller as camera zoom increases", () => {
    expect(markerScaleForZoom(1)).toBeGreaterThan(markerScaleForZoom(2));
    expect(markerScaleForZoom(2)).toBeGreaterThan(markerScaleForZoom(4));
    expect(markerScaleForZoom(100)).toBeGreaterThanOrEqual(0.18);
  });

  it("interpolates active curve-track values at the backend-selected MD", () => {
    const value = interpolateCurveValueAtMd([
      { md: 1000, value: 10, normalized: 0 },
      { md: 1100, value: 30, normalized: 1 },
    ], 1050);
    expect(value).toBeCloseTo(20, 8);
  });
});
