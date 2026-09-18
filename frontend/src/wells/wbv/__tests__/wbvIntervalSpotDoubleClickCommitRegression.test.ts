/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";

describe("WBV Interval Selection spot double-click", () => {
  const downStart = renderer.indexOf("const handlePointerDown = (event: PointerEvent) =>");
  const moveStart = renderer.indexOf("const handlePointerMove = (event: PointerEvent) =>", downStart);
  const downBlock = renderer.slice(downStart, moveStart);

  it("does not suppress the second pointerdown in Interval Selection", () => {
    expect(downBlock).toContain(
      "if (event.detail >= 2 && selectionModeRef.current !== 'interval')",
    );
  });

  it("still suppresses ordinary double-click behavior outside interval mode", () => {
    expect(downBlock).toContain("event.preventDefault()");
    expect(downBlock).toContain("event.stopPropagation()");
  });

  it("keeps the interval pointer-up exact-pick path intact", () => {
    const intervalStart = renderer.indexOf("if (selectionModeRef.current === 'interval')");
    const cancelStart = renderer.indexOf("const handlePointerCancel", intervalStart);
    const block = renderer.slice(intervalStart, cancelStart);
    expect(block).toContain("const projection = localProjectionFor(event)");
    expect(block).toContain("exactObservationForProjection(projection)");
    expect(block).toContain("sendCommand({ kind: 'observe'");
  });
});
