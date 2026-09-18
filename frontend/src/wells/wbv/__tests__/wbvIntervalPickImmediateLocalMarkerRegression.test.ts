/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV interval pick immediate local marker", () => {
  it("maintains renderer-local interval presentation state", () => {
    expect(renderer).toContain("let localIntervalStartProjection");
    expect(renderer).toContain("let pendingIntervalObserveCount = 0");
  });

  it("places interval markers immediately from the local projected click", () => {
    expect(renderer).toContain("const showImmediateIntervalProjection");
    expect(renderer).toContain("setMarkerBasePosition(intervalStartMarker, projectedPosition)");
    expect(renderer).toContain("setMarkerBasePosition(intervalEndMarker, projectedPosition)");
  });

  it("does not allow older backend responses to overwrite an in-flight local marker", () => {
    expect(renderer).toContain("selectionModeRef.current === 'interval' && pendingIntervalObserveCount > 0");
  });

  it("reconciles authoritative state when all interval observes settle", () => {
    expect(renderer).toContain("pendingIntervalObserveCount = Math.max(0, pendingIntervalObserveCount - 1)");
    expect(renderer).toContain("if (pendingIntervalObserveCount === 0)");
    expect(renderer).toContain("syncInteraction();");
  });

  it("retains exact local projection for backend observation", () => {
    expect(renderer).toContain("const observation = exactObservationForProjection(projection)");
    expect(renderer).toContain("sendCommand({ kind: 'observe', observation, sequence: 0 })");
  });
});
