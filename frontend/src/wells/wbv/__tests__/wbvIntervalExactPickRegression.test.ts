/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV interval exact pick regression", () => {
  const intervalStart = renderer.indexOf("if (selectionModeRef.current === 'interval')");
  const fallbackStart = renderer.indexOf(
    "const observation = observationFor(event)",
    intervalStart,
  );
  const intervalBlock =
    intervalStart >= 0 && fallbackStart > intervalStart
      ? renderer.slice(intervalStart, fallbackStart)
      : "";

  it("uses exact projected wellbore locator geometry for interval picks", () => {
    expect(intervalStart).toBeGreaterThanOrEqual(0);
    expect(intervalBlock).toContain("const projection = localProjectionFor(event)");
    expect(intervalBlock).toContain(
      "const observation = exactObservationForProjection(projection)",
    );
    expect(intervalBlock).toContain(
      "void sendCommand({ kind: 'observe', observation, sequence: 0 })",
    );
  });

  it("keeps raw pointer observation outside the interval-specific branch", () => {
    expect(intervalBlock).not.toContain("observationFor(event)");
    expect(fallbackStart).toBeGreaterThan(intervalStart);
  });
});
