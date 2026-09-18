/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV Interval Selection orbit release", () => {
  const start = renderer.indexOf("if (selectionModeRef.current === 'interval')");
  const fallback = renderer.indexOf("const observation = observationFor(event)", start);
  const block = renderer.slice(start, fallback);

  it("preserves exact interval projection", () => {
    expect(block).toContain("const projection = localProjectionFor(event)");
    expect(block).toContain("exactObservationForProjection(projection)");
    expect(block).toContain("sendCommand({ kind: 'observe'");
  });

  it("does not swallow pointerup from OrbitControls", () => {
    expect(block).not.toContain("event.preventDefault()");
    expect(block).not.toContain("event.stopPropagation()");
  });
});
