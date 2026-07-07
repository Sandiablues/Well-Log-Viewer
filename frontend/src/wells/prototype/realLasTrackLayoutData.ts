import type { CurveCatalogItem, WellHeader, WellLogTrack } from './trackLayoutModel';

/*
 * No well-specific runtime fixture is permitted here.
 * Live WDV data must come from backend-owned managed contracts.
 */
export const fullDepthRange = { min: 0, max: 1 };
export const defaultDepthRange = { min: 0, max: 1 };
export const depthUnitLabel = '';

export const wellHeader = {} as WellHeader;
export const curveCatalog: CurveCatalogItem[] = [];

export const initialTracks: WellLogTrack[] = [];

export type RealCurveSample = readonly [number, number];
export const realCurveSamplesByCurveId: Record<string, RealCurveSample[]> = {};
