/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Information spot/lithology/core refinement", () => {
  it("recognizes zero-length selection as a spot", () => {
    expect(page).toContain("const selectedInformationIsSpot");
    expect(page).toContain("Math.abs(selectedInformationBaseMd - selectedInformationTopMd) <= 1e-6");
    expect(page).toContain('"Selected spot"');
  });

  it("shows one curve value for a spot", () => {
    expect(page).toContain("selectedInformationIsSpot");
    expect(page).toContain("formatNumber(curve.maximum, 3)");
  });

  it("resolves canonical lithology IDs through Knowledge Repository but hides internal metadata", () => {
    expect(page).toContain("/api/wlv/knowledge/lithology/entries/");
    expect(page).toContain("knowledge?.name");
    const lithologyStart = page.indexOf("intervalLithology.map");
    const curveStart = page.indexOf('aria-label="Curve information"', lithologyStart);
    const lithologyBlock = page.slice(lithologyStart, curveStart);
    expect(lithologyBlock).not.toContain("knowledge?.description");
    expect(lithologyBlock).not.toContain("knowledge?.fgdcCode");
    expect(lithologyBlock).not.toContain("FGDC ");
  });

  it("collapses core segments under the Core Image disclosure", () => {
    expect(page).toContain('<details className="wlv-wbv-interval-information__core-disclosure"');
    expect(page).toContain('<summary className="wlv-wbv-interval-information__core-summary">');
    expect(page).toContain('className="wlv-wbv-interval-information__core-chevron"');
    expect(page).toContain("fileDescriptions");
  });
});
