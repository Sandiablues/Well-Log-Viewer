/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import renderer from "../WellboreTrajectoryRenderer.tsx?raw";
import css from "../Wellbore3DPage.css?raw";

describe("WBV zoom range and compact Manage button", () => {
  it("allows substantially closer orthographic zoom", () => {
    expect(renderer).toContain("controls.maxZoom = 40;");
    expect(renderer).toContain("controls.minZoom = 0.35;");
  });

  it("keeps the Display Layers Manage button compact without changing other buttons", () => {
    expect(css).toContain(".wlv-wbv-manage-layers-button {");
    expect(css).toContain("min-height: 1.28rem;");
    expect(css).toContain("font-size: 0.58rem;");
  });
});
