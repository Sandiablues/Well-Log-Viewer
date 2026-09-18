/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Core spot metadata resolution", () => {
  const start = page.indexOf("const intervalCoreFiles = useMemo");
  const end = page.indexOf("const intervalActiveCurveProductIds = useMemo", start);
  const block = page.slice(start, end);

  it("collects all selected Core Image description observations before spatial filtering", () => {
    expect(block).toContain("const candidates: WbvCoreDescriptionItem[] = []");
    expect(block).toContain("candidates.push({");
  });

  it("uses nearest Core description for an exact spot interrogation", () => {
    expect(block).toContain("if (selectedInformationIsSpot && selectedInformationSpotMd != null)");
    expect(block).toContain("const nearestByProduct = new Map");
    expect(block).toContain("distance < current.distance");
  });

  it("returns one nearest observation per active Core Image product", () => {
    expect(block).toContain("nearestByProduct.set(item.product_id");
    expect(block).toContain("Array.from(nearestByProduct.values()).map");
  });

  it("preserves normal interval intersection behavior", () => {
    expect(block).toContain("item.base_md >= selectedInformationTopMd && item.top_md <= selectedInformationBaseMd");
  });
});
