/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV Core camera-facing model rotation V1.0.1", () => {
  const start = renderer.indexOf("function addCoreImageTracks(");
  const end = renderer.indexOf("const krLithologyEntryCache", start);
  const core = renderer.slice(start, end);

  it("uses the compile-proven world-to-local camera basis for Core", () => {
    expect(core).toContain("const coreLocalCameraRight = (camera: THREE.Camera): THREE.Vector3 => {");
    expect(core).toContain("const worldToLocalQuaternion = groupWorldQuaternion.clone().invert();");
    expect(core).toContain(".applyQuaternion(worldToLocalQuaternion)");
  });

  it("does not suppress Core locator rebuilds with a camera-only cache", () => {
    expect(core).not.toContain("lastLocatorCameraQuaternion");
    expect(core).not.toContain("angleTo(camera.quaternion)");
    expect(core).toContain("const cameraRight = coreLocalCameraRight(camera);");
  });

  it("projects Core pick candidates through the current model transform", () => {
    expect(core).toContain("const local = basis.position.clone().add(axis.multiplyScalar(resolvedCenterOffset));");
    expect(core).toContain("const world = local.applyMatrix4(group.matrixWorld);");
  });

  it("retains the outer camera-or-model orientation refresh", () => {
    expect(renderer).toContain("if (cameraOrientationChanged || modelOrientationChanged)");
    expect(renderer).toContain("coreTrackRuntime.update(camera);");
  });
});
