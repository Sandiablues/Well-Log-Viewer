/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Core spot direct coverage gate", () => {
  const start = page.indexOf("let descriptions: WbvCoreDescriptionItem[];");
  const end = page.indexOf("descriptions.sort", start);
  const block = page.slice(start, end);

  it("requires direct Core Image product coverage for spot metadata", () => {
    expect(block).toContain("const directlyCoveredCoreProductIds = new Set");
    expect(block).toContain("selectedInformationSpotMd >= coverageTop");
    expect(block).toContain("selectedInformationSpotMd <= coverageBase");
  });

  it("does not consider nearest descriptions from uncovered Core products", () => {
    expect(block).toContain("if (!directlyCoveredCoreProductIds.has(item.product_id)) continue;");
  });

  it("retains nearest stored description behavior inside covered Core", () => {
    expect(block).toContain("const nearestByProduct = new Map");
    expect(block).toContain("distance < current.distance");
  });

  it("preserves normal interval intersection behavior", () => {
    expect(block).toContain("item.base_md >= selectedInformationTopMd && item.top_md <= selectedInformationBaseMd");
  });
});
