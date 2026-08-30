import type { WellLogTrack } from '../prototype/trackLayoutModel';
import type {
  FormationTopMarker,
  FormationTopOverlayStyle,
  LithologyIntervalRecord,
} from './WdvPresentationPrimitives';
import type { CurveFillGeometryV2 } from './curveFillV2';

export type WellOwnedOverlayRenderState = {
  formationTops: FormationTopMarker[];
  allFormationTops: FormationTopMarker[];
  lithologyIntervals: LithologyIntervalRecord[];
  loadedLithologyIntervals: LithologyIntervalRecord[];
  formationTopOverlayStylesByTrackId: Record<string, FormationTopOverlayStyle>;
};

export type WellOwnedTrackRenderBundle = WellOwnedOverlayRenderState & {
  managedWellUid: string;
  curveFillGeometryByRuleUid: ReadonlyMap<string, CurveFillGeometryV2>;
};

export const EMPTY_WELL_OWNED_TRACK_RENDER_BUNDLE: WellOwnedTrackRenderBundle = {
  managedWellUid: '',
  formationTops: [],
  allFormationTops: [],
  lithologyIntervals: [],
  loadedLithologyIntervals: [],
  formationTopOverlayStylesByTrackId: {},
  curveFillGeometryByRuleUid: new Map(),
};

export function buildWellOwnedTrackRenderBundles(
  overlaysByWellUid: Readonly<Record<string, WellOwnedOverlayRenderState>>,
  curveFillGeometryByRuleUid: ReadonlyMap<string, CurveFillGeometryV2>,
  activeTracks: readonly Pick<WellLogTrack, 'trackId' | 'managedWellUid'>[] = [],
): ReadonlyMap<string, WellOwnedTrackRenderBundle> {
  const activeTrackUids = new Set(activeTracks.map((track) => track.trackId));
  const geometriesByWellUid = new Map<string, Map<string, CurveFillGeometryV2>>();
  for (const [ruleUid, geometry] of curveFillGeometryByRuleUid.entries()) {
    if (!activeTrackUids.has(geometry.track_uid)) continue;
    const wellUid = geometry.managed_well_uid;
    if (!wellUid) continue;
    let geometryMap = geometriesByWellUid.get(wellUid);
    if (!geometryMap) {
      geometryMap = new Map();
      geometriesByWellUid.set(wellUid, geometryMap);
    }
    geometryMap.set(ruleUid, geometry);
  }

  const wellUids = new Set<string>([
    ...Object.keys(overlaysByWellUid),
    ...geometriesByWellUid.keys(),
  ]);
  const bundles = new Map<string, WellOwnedTrackRenderBundle>();
  for (const wellUid of wellUids) {
    const overlays = overlaysByWellUid[wellUid];
    bundles.set(wellUid, {
      managedWellUid: wellUid,
      formationTops: overlays?.formationTops ?? [],
      allFormationTops: overlays?.allFormationTops ?? [],
      lithologyIntervals: overlays?.lithologyIntervals ?? [],
      loadedLithologyIntervals: overlays?.loadedLithologyIntervals ?? [],
      formationTopOverlayStylesByTrackId: overlays?.formationTopOverlayStylesByTrackId ?? {},
      curveFillGeometryByRuleUid: geometriesByWellUid.get(wellUid) ?? new Map(),
    });
  }
  return bundles;
}

export function renderBundleForTrack(
  track: Pick<WellLogTrack, 'managedWellUid'>,
  bundlesByWellUid: ReadonlyMap<string, WellOwnedTrackRenderBundle>,
): WellOwnedTrackRenderBundle {
  const wellUid = track.managedWellUid;
  if (!wellUid) return EMPTY_WELL_OWNED_TRACK_RENDER_BUNDLE;
  return bundlesByWellUid.get(wellUid) ?? EMPTY_WELL_OWNED_TRACK_RENDER_BUNDLE;
}
