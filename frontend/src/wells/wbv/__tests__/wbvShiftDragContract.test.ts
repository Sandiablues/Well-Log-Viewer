import { describe, expect, it } from "vitest";
import rendererSource from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV Shift-MB1 selector drag contract", () => {
  it("keeps the active drag alive across backend interaction-state rerenders", () => {
    expect(rendererSource).toContain("const onPointSelectRef = useRef(onPointSelect)");
    expect(rendererSource).toContain("onPointSelectRef.current = onPointSelect");
    expect(rendererSource).toContain("const command = onPointSelectRef.current");

    const sceneEffectDependencies = rendererSource.slice(
      rendererSource.indexOf("  }, [\n    curveOverlays"),
      rendererSource.indexOf("  useEffect(() => {\n    runtimeRef.current?.syncInteraction()"),
    );
    expect(sceneEffectDependencies).not.toContain("\n    onPointSelect,");

    expect(rendererSource).toContain("event.shiftKey && selectionModeRef.current === 'point'");
    expect(rendererSource).toContain("renderer.domElement.setPointerCapture(event.pointerId)");
    expect(rendererSource).toContain("addEventListener('pointermove', handlePointerMove, true)");
    expect(rendererSource).toContain("pendingDragPoint = point");
    expect(rendererSource).toContain("if (controls) controls.enabled = true");
  });

  it("uses an always-front screen-facing bullseye sprite instead of coplanar ring meshes", () => {
    expect(rendererSource).toContain("new THREE.SpriteMaterial");
    expect(rendererSource).toContain("depthTest: false");
    expect(rendererSource).toContain("const marker = new THREE.Sprite(material)");
    expect(rendererSource).toContain("marker.renderOrder = 200");
    expect(rendererSource).toContain("rgba(4, 8, 11, 0.82)");
    expect(rendererSource).toContain("markerScaleForZoom(camera.zoom)");
    expect(rendererSource).not.toContain("new THREE.RingGeometry");
  });
});

it("renders a frame-rate drag preview while throttling backend confirmation", () => {
  expect(rendererSource).toContain("const DRAG_BACKEND_INTERVAL_MS = 75");
  expect(rendererSource).toContain("const setDragPreview = (point: WbvTrajectoryRenderPoint)");
  expect(rendererSource).toContain("selectedRuntimePoint = point");
  expect(rendererSource).toContain("if (picked) queueDragPick(picked)");
  expect(rendererSource).toContain("performance.now() - lastDragDispatchAt");
  expect(rendererSource).toContain("window.setTimeout(() =>");
  expect(rendererSource).toContain("if (finalPoint) queueDragPick(finalPoint, true)");
  expect(rendererSource).toContain("interpolateCurveValueAtMd(curve.samples, currentPoint.md as number)");
});
