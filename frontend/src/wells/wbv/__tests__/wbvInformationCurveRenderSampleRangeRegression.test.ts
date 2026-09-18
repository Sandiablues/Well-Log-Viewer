/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Information curve interval/spot range source", () => {
  const start = page.indexOf("const renderCurveById = new Map");
  const end = page.indexOf("const intervalInformationHasResults", start);
  const block = page.slice(start, end);

  it("uses committed render-package samples", () => {
    expect(block).toContain("renderCurve?.samples");
    expect(block).toContain("validSamples.filter((sample) => sample.md >= topMd && sample.md <= baseMd)");
  });

  it("uses nearest committed sample for a spot", () => {
    expect(block).toContain("nearestDistance");
    expect(block).toContain("Math.abs(sample.md - selectedInformationSpotMd)");
  });

  it("retains inventory lookup only as legacy fallback", () => {
    expect(block).toContain("Promise.all(legacyCurveIds.map");
    expect(block).toContain("/curve-samples?product_id=");
  });
});
