/**
 * WBV canonical depth-unit foundation.
 *
 * IMPORTANT:
 * - This module is intentionally NOT wired into current WBV runtime behavior.
 * - Canonical runtime depth is metres.
 * - Display unit conversion belongs at presentation/input boundaries only.
 * - Three.js/model-space geometry must never be transformed by display-unit changes.
 */

export type WbvCanonicalDepthUnit = "m";
export type WbvDisplayDepthUnit = "m" | "ft";
export type WbvSupportedSourceDepthUnit = "m" | "ft";

export const WBV_CANONICAL_DEPTH_UNIT: WbvCanonicalDepthUnit = "m";
export const METRES_TO_FEET = 3.280839895013123;
export const FEET_TO_METRES = 1 / METRES_TO_FEET;

function assertFinite(value: number, name = "value"): number {
  if (!Number.isFinite(value)) {
    throw new Error(`${name} must be finite`);
  }
  return value;
}

export function normalizeDepthUnit(value: unknown): WbvDisplayDepthUnit | null {
  const raw = String(value ?? "").trim().toLowerCase();
  if (raw === "m" || raw === "meter" || raw === "meters" || raw === "metre" || raw === "metres") {
    return "m";
  }
  if (raw === "ft" || raw === "foot" || raw === "feet") {
    return "ft";
  }
  return null;
}

export function sourceDepthToCanonical(
  value: number,
  sourceUnit: WbvSupportedSourceDepthUnit,
): number {
  assertFinite(value);
  return sourceUnit === "m" ? value : value * FEET_TO_METRES;
}

export function canonicalDepthToDisplay(
  canonicalMetres: number,
  displayUnit: WbvDisplayDepthUnit,
): number {
  assertFinite(canonicalMetres, "canonicalMetres");
  return displayUnit === "m" ? canonicalMetres : canonicalMetres * METRES_TO_FEET;
}

export function displayDepthToCanonical(
  displayValue: number,
  displayUnit: WbvDisplayDepthUnit,
): number {
  assertFinite(displayValue, "displayValue");
  return displayUnit === "m" ? displayValue : displayValue * FEET_TO_METRES;
}

export interface WbvCanonicalDepthInterval {
  top_md_m: number;
  base_md_m: number;
}

export interface WbvDisplayDepthInterval {
  top_md: number;
  base_md: number;
  depth_unit: WbvDisplayDepthUnit;
}

export function canonicalIntervalToDisplay(
  interval: WbvCanonicalDepthInterval,
  displayUnit: WbvDisplayDepthUnit,
): WbvDisplayDepthInterval {
  return {
    top_md: canonicalDepthToDisplay(interval.top_md_m, displayUnit),
    base_md: canonicalDepthToDisplay(interval.base_md_m, displayUnit),
    depth_unit: displayUnit,
  };
}

export function displayIntervalToCanonical(
  topMd: number,
  baseMd: number,
  displayUnit: WbvDisplayDepthUnit,
): WbvCanonicalDepthInterval {
  return {
    top_md_m: displayDepthToCanonical(topMd, displayUnit),
    base_md_m: displayDepthToCanonical(baseMd, displayUnit),
  };
}

/**
 * Coordinate readout conversion ONLY.
 * Never use this function to mutate renderer/model-space coordinates.
 */
export function canonicalCoordinateReadoutToDisplay(
  canonicalMetres: number,
  displayUnit: WbvDisplayDepthUnit,
): number {
  return canonicalDepthToDisplay(canonicalMetres, displayUnit);
}

/**
 * Canonical dogleg value is degrees per 30 metres.
 * Display in degrees/30m for metric or degrees/100ft for imperial.
 */
export function canonicalDoglegToDisplay(
  degreesPer30m: number,
  displayUnit: WbvDisplayDepthUnit,
): number {
  assertFinite(degreesPer30m, "degreesPer30m");
  if (displayUnit === "m") return degreesPer30m;
  const metresPer100Ft = 100 * FEET_TO_METRES;
  return degreesPer30m * (metresPer100Ft / 30);
}

export function formatDepth(
  canonicalMetres: number,
  displayUnit: WbvDisplayDepthUnit,
  decimals = 2,
): string {
  return `${canonicalDepthToDisplay(canonicalMetres, displayUnit).toFixed(decimals)} ${displayUnit}`;
}

/**
 * Round-trip helper used by regression tests.
 * Returned value is canonical metres.
 */
export function displayRoundTrip(
  canonicalMetres: number,
  toUnit: WbvDisplayDepthUnit,
): number {
  return displayDepthToCanonical(
    canonicalDepthToDisplay(canonicalMetres, toUnit),
    toUnit,
  );
}
