/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Information Panel visual cleanup V1.0.1", () => {
  it("shows useful lithology text only and hides internal KR/FGDC identifiers", () => {
    const lithologyStart = page.indexOf("intervalLithology.map");
    const curveStart = page.indexOf("aria-label=\"Curve information\"", lithologyStart);
    const lithologyBlock = page.slice(lithologyStart, curveStart);
    expect(lithologyBlock).toContain("knowledge?.name");
    expect(lithologyBlock).not.toContain("knowledge?.description");
    expect(lithologyBlock).not.toContain("knowledge?.fgdcCode");
    expect(lithologyBlock).not.toContain("FGDC ");
    expect(lithologyBlock).not.toContain("|| canonicalId");
  });

  it("keeps CURVES as a normal visible section, not a disclosure", () => {
    const curveStart = page.indexOf("aria-label=\"Curve information\"");
    const coreStart = page.indexOf('aria-label="Core information"', curveStart);
    const curveBlock = page.slice(curveStart, coreStart);
    expect(curveBlock).toContain("<h3>Curves</h3>");
    expect(curveBlock).not.toContain("curve-disclosure");
    expect(curveBlock).not.toContain("disclosure-chevron");
  });

  it("puts the explicit disclosure chevron beside Core Image", () => {
    expect(page).toContain('className="wlv-wbv-interval-information__core-title"');
    expect(page).toContain('className="wlv-wbv-interval-information__core-chevron"');
    expect(page).toContain("<strong>{file.display_name}</strong>");
  });
});
