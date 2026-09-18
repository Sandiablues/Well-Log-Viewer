/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import page from "../Wellbore3DPage.tsx?raw";

describe("WBV Core Image title white styling", () => {
  it("keeps Core Image inside the dedicated core-title wrapper", () => {
    expect(page).toContain('className="wlv-wbv-interval-information__core-title"');
    expect(page).toContain("<strong>{file.display_name}</strong>");
  });
});
