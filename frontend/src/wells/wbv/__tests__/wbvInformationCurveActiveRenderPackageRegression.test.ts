/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Information curve authority", () => {
  const start = page.indexOf("const intervalActiveCurveProductIds = useMemo");
  const end = page.indexOf("const intervalInformationHasResults", start);
  const block = page.slice(start, end);

  it("uses committed published render-package curves as primary active authority", () => {
    expect(block).toContain("curveOverlayRenderPackage?.curves");
    expect(block).toContain("publishedCurveIds.length > 0");
  });

  it("keeps selected_item_ids only as legacy fallback", () => {
    expect(block).toContain(": committedCurveConfig.selected_item_ids");
  });

  it("preserves interval min/max while supporting spot-value mode", () => {
    expect(block).toContain("const intervalMinimum = Math.min(...values)");
    expect(block).toContain("const intervalMaximum = Math.max(...values)");
    expect(block).toContain("selectedInformationIsSpot ? intervalMaximum : intervalMinimum");
  });

  it("does not require Display Layers visibility", () => {
    expect(block).not.toContain("committedCurveConfig.visible");
  });
});
