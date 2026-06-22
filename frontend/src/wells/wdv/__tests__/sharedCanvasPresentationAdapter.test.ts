/**
 * Unit tests for buildSharedCanvasPresentationModel and extractBoundCurveUids.
 *
 * Covers 17 required criteria:
 *  1.  depth_min/max → fullDepthRange.min/max
 *  2.  Tracks sorted by track_order ascending
 *  3.  Slots sorted by slot_order within each track
 *  4.  Only BOUND slots produce a CurveAssignment
 *  5.  UNAVAILABLE slot omitted from curves[]; track still present
 *  6.  UNRESOLVED slot omitted from curves[]; track still present
 *  7.  Numeric scale_min/scale_max on CurveAssignment (not labels)
 *  8.  scale_min_label/scale_max_label on CurveAssignment (display only)
 *  9.  managed_curve_uid on BOUND CurveAssignment
 * 10.  Depth track (track_type 'depth') → DepthTrack in output
 * 11.  Track with only non-BOUND slots → CurveTrack with empty curves[]
 * 12.  depth_unit ('m'|'ft') propagated to DepthTrack.unit
 * 13.  WellHeader logStart/logEnd = String(depth_min/max)
 * 14.  Samples keyed by managed_curve_uid in curveSamplesByCurveId
 * 15.  managedWellUid = session.managed_well_uid
 * 16.  revision = profile_revision_number
 * 17.  Track width_px propagated to WellLogTrack.widthPx
 */

import { describe, expect, it } from 'vitest';
import type {
  ManagedCurveUid,
} from '../../identity/wdvIdentityV21';
import type {
  ManagedCurveSamplesByUidV21,
  ManagedCurveSampleV21,
} from '../../prototype/managedCurveSamplesV21';
import type {
  CurveTrack,
  DepthTrack,
} from '../../prototype/trackLayoutModel';
import {
  buildSharedCanvasPresentationModel,
  extractBoundCurveUids,
} from '../sharedCanvasPresentationAdapter';
import type {
  ResolvedWdvCanvasSession,
  SharedCanvasResolvedSlot,
  SharedCanvasResolvedTrack,
} from '../sharedCanvasApiTypes';


// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------

function makeSession(
  overrides: Partial<ResolvedWdvCanvasSession> = {},
): ResolvedWdvCanvasSession {
  return {
    managed_well_uid: 'well-001',
    profile_uid: 'prof-001',
    profile_revision_uid: 'rev-001',
    profile_revision_number: 3,
    activation_scope_type: 'local_workspace',
    activation_scope_uid: 'ws-001',
    resolved_tracks: [],
    binding_summary: {
      total_slots: 0, bound: 0, unavailable: 0, unresolved: 0,
      excluded: 0, incompatible: 0, user_unbound: 0, stale_binding: 0,
    },
    warnings: [],
    updated_at: '2026-01-01T00:00:00Z',
    depth_min: 100.0,
    depth_max: 3500.0,
    depth_unit: 'ft',
    ...overrides,
  };
}

function makeTrack(
  overrides: Partial<SharedCanvasResolvedTrack> = {},
): SharedCanvasResolvedTrack {
  return {
    track_uid: 'track-001',
    track_key: null,
    track_order: 0,
    track_name: 'Test Track',
    track_type: 'curve',
    track_role: null,
    renderer_type: null,
    width_px: 200,
    lattice: 'linear',
    lattice_source: 'front_curve_default',
    scale_mode: 'per_curve',
    depth_basis: null,
    slots: [],
    ...overrides,
  };
}

function makeBoundSlot(
  overrides: Partial<SharedCanvasResolvedSlot> = {},
): SharedCanvasResolvedSlot {
  return {
    slot_uid: 'slot-001',
    slot_key: 'GR',
    slot_order: 0,
    binding_status: 'bound',
    managed_curve_uid: 'curve-001',
    display_name: 'Gamma Ray',
    mnemonic: 'GR',
    curve_family: 'gamma_ray',
    kr_curve_type_id: 'gamma_ray',
    unit: 'gAPI',
    scale_min: 0.0,
    scale_max: 150.0,
    scale_min_label: '0',
    scale_max_label: '150',
    warnings: [],
    ...overrides,
  };
}

function makeUnavailableSlot(
  overrides: Partial<SharedCanvasResolvedSlot> = {},
): SharedCanvasResolvedSlot {
  return {
    slot_uid: 'slot-unavail',
    slot_key: 'DT',
    slot_order: 1,
    binding_status: 'unavailable',
    managed_curve_uid: null,
    display_name: null,
    mnemonic: null,
    curve_family: null,
    kr_curve_type_id: null,
    unit: null,
    scale_min: null,
    scale_max: null,
    scale_min_label: null,
    scale_max_label: null,
    warnings: [],
    ...overrides,
  };
}

function makeSamples(
  curveUid: string,
  points: [number, number][],
): ManagedCurveSamplesByUidV21 {
  const samples: ManagedCurveSampleV21[] = points.map(
    ([depth, value]) => ({ depth, value }),
  );
  return new Map([[curveUid as ManagedCurveUid, samples]]);
}


// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('buildSharedCanvasPresentationModel', () => {

  // Test 1 — depth_min/max → fullDepthRange
  it('depth_min/max flow into fullDepthRange', () => {
    const session = makeSession({ depth_min: 250.5, depth_max: 4100.0 });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.fullDepthRange.min).toBe(250.5);
    expect(model.fullDepthRange.max).toBe(4100.0);
  });

  // Test 2 — tracks sorted by track_order ascending
  it('outputs tracks in ascending track_order regardless of input order', () => {
    const t0 = makeTrack({ track_uid: 'ta', track_order: 0, track_name: 'First' });
    const t1 = makeTrack({ track_uid: 'tb', track_order: 1, track_name: 'Second' });
    const t2 = makeTrack({ track_uid: 'tc', track_order: 2, track_name: 'Third' });
    // Supply in reverse order
    const session = makeSession({ resolved_tracks: [t2, t0, t1] });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.tracks.map((t) => t.trackIndex)).toEqual([0, 1, 2]);
    expect(model.tracks.map((t) => t.title)).toEqual(['First', 'Second', 'Third']);
  });

  // Test 3 — slots sorted by slot_order within a track
  it('sorts CurveAssignments by slot_order within each CurveTrack', () => {
    const s0 = makeBoundSlot({ slot_uid: 's0', slot_order: 0, managed_curve_uid: 'c0' });
    const s1 = makeBoundSlot({ slot_uid: 's1', slot_order: 1, managed_curve_uid: 'c1' });
    const s2 = makeBoundSlot({ slot_uid: 's2', slot_order: 2, managed_curve_uid: 'c2' });
    const track = makeTrack({ slots: [s2, s0, s1] });  // reversed
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.curves.map((c) => c.stackIndex)).toEqual([0, 1, 2]);
    expect(curveTrack.curves.map((c) => c.curveId)).toEqual(['c0', 'c1', 'c2']);
  });

  // Test 4 — only BOUND slots produce a CurveAssignment
  it('only BOUND slots produce CurveAssignment entries', () => {
    const bound = makeBoundSlot({ slot_uid: 'bound', managed_curve_uid: 'c-bound' });
    const unavail = makeUnavailableSlot({ slot_uid: 'unavail' });
    const track = makeTrack({ slots: [bound, unavail] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.curves).toHaveLength(1);
    expect(curveTrack.curves[0].curveId).toBe('c-bound');
  });

  // Test 5 — UNAVAILABLE slot omitted from curves[]; track still present
  it('UNAVAILABLE slot is omitted from curves[] but track is retained', () => {
    const slot = makeUnavailableSlot();
    const track = makeTrack({ track_uid: 'track-x', slots: [slot] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.tracks).toHaveLength(1);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.trackType).toBe('curve');
    expect(curveTrack.curves).toHaveLength(0);
  });

  // Test 6 — UNRESOLVED slot omitted from curves[]; track still present
  it('UNRESOLVED slot is omitted from curves[] but track is retained', () => {
    const slot: SharedCanvasResolvedSlot = {
      ...makeUnavailableSlot(),
      binding_status: 'unresolved',
      slot_uid: 'unresolved-slot',
    };
    const track = makeTrack({ slots: [slot] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.curves).toHaveLength(0);
  });

  // Test 7 — numeric scale_min/scale_max on CurveAssignment
  it('numeric scale_min/scale_max retained verbatim on CurveAssignment', () => {
    const slot = makeBoundSlot({ scale_min: 10.5, scale_max: 280.75 });
    const track = makeTrack({ slots: [slot] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.curves[0].scaleMin).toBe(10.5);
    expect(curveTrack.curves[0].scaleMax).toBe(280.75);
  });

  // Test 8 — scale labels on CurveAssignment
  it('scale_min_label and scale_max_label propagated to CurveAssignment', () => {
    const slot = makeBoundSlot({
      scale_min: 0.5,
      scale_max: 38.86,
      scale_min_label: '0.5',
      scale_max_label: '38.9',
    });
    const track = makeTrack({ slots: [slot] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.curves[0].scaleMinLabel).toBe('0.5');
    expect(curveTrack.curves[0].scaleMaxLabel).toBe('38.9');
  });

  // Test 9 — managed_curve_uid on BOUND CurveAssignment
  it('BOUND slot managed_curve_uid appears on CurveAssignment', () => {
    const curveUid = 'curve-abc-123';
    const slot = makeBoundSlot({ managed_curve_uid: curveUid });
    const track = makeTrack({ slots: [slot] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.curves[0].curveId).toBe(curveUid);
    expect(curveTrack.curves[0].curveUid).toBe(curveUid);
  });

  // Test 10 — depth track produces DepthTrack output
  it('track_type "depth" produces a DepthTrack', () => {
    const track = makeTrack({
      track_uid: 'depth-track',
      track_type: 'depth',
      depth_basis: 'MD',
    });
    const session = makeSession({ resolved_tracks: [track], depth_unit: 'ft' });
    const model = buildSharedCanvasPresentationModel(session);
    const depthTrack = model.tracks[0] as DepthTrack;
    expect(depthTrack.trackType).toBe('depth');
    expect(depthTrack.depthBasis).toBe('MD');
  });

  // Test 11 — track with only non-BOUND slots → CurveTrack with empty curves
  it('CurveTrack with all-unavailable slots has empty curves array', () => {
    const slots = [
      makeUnavailableSlot({ slot_uid: 's1' }),
      { ...makeUnavailableSlot({ slot_uid: 's2' }), binding_status: 'unresolved' as const },
    ];
    const track = makeTrack({ slots });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    const curveTrack = model.tracks[0] as CurveTrack;
    expect(curveTrack.trackType).toBe('curve');
    expect(curveTrack.curves).toHaveLength(0);
  });

  // Test 12 — depth_unit propagated to DepthTrack.unit
  it('depth_unit "m" propagates to DepthTrack.unit', () => {
    const track = makeTrack({ track_type: 'depth' });
    const session = makeSession({ resolved_tracks: [track], depth_unit: 'm' });
    const model = buildSharedCanvasPresentationModel(session);
    const depthTrack = model.tracks[0] as DepthTrack;
    expect(depthTrack.unit).toBe('m');
  });

  it('depth_unit "ft" propagates to DepthTrack.unit', () => {
    const track = makeTrack({ track_type: 'depth' });
    const session = makeSession({ resolved_tracks: [track], depth_unit: 'ft' });
    const model = buildSharedCanvasPresentationModel(session);
    const depthTrack = model.tracks[0] as DepthTrack;
    expect(depthTrack.unit).toBe('ft');
  });

  // Test 13 — WellHeader logStart/logEnd = String(depth_min/max)
  it('WellHeader logStart/logEnd mirror depth_min/max as strings', () => {
    const session = makeSession({ depth_min: 100.5, depth_max: 3000.25 });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.wellHeader.logStart).toBe('100.5');
    expect(model.wellHeader.logEnd).toBe('3000.25');
  });

  // Test 14 — samples keyed by managed_curve_uid appear in curveSamplesByCurveId
  it('samples appear in curveSamplesByCurveId keyed by managed_curve_uid', () => {
    const curveUid = 'curve-samples-test';
    const samples = makeSamples(curveUid, [[100, 45], [200, 67]]);
    const session = makeSession();
    const model = buildSharedCanvasPresentationModel(session, samples);
    const loaded = model.curveSamplesByCurveId[curveUid];
    expect(loaded).toBeDefined();
    expect(loaded).toHaveLength(2);
    expect(loaded[0]).toEqual([100, 45]);
    expect(loaded[1]).toEqual([200, 67]);
  });

  // Test 15 — managedWellUid = session.managed_well_uid
  it('managedWellUid matches session.managed_well_uid', () => {
    const session = makeSession({ managed_well_uid: 'well-xyz-456' });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.managedWellUid).toBe('well-xyz-456');
  });

  // Test 16 — revision = profile_revision_number
  it('revision equals profile_revision_number', () => {
    const session = makeSession({ profile_revision_number: 7 });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.revision).toBe(7);
  });

  // Test 17 — track width_px propagated to WellLogTrack.widthPx
  it('track width_px propagates to WellLogTrack.widthPx', () => {
    const track = makeTrack({ width_px: 320 });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.tracks[0].widthPx).toBe(320);
  });

  // Additional: width_px null falls back to default (150)
  it('null width_px falls back to 150', () => {
    const track = makeTrack({ width_px: null });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.tracks[0].widthPx).toBe(150);
  });

  // curveCatalog contains only BOUND curves
  it('curveCatalog contains only BOUND slots', () => {
    const bound = makeBoundSlot({ managed_curve_uid: 'bound-curve' });
    const unavail = makeUnavailableSlot();
    const track = makeTrack({ slots: [bound, unavail] });
    const session = makeSession({ resolved_tracks: [track] });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.curveCatalog).toHaveLength(1);
    expect(model.curveCatalog[0].curveId).toBe('bound-curve');
  });

  // Empty session → empty tracks
  it('session with no tracks produces empty tracks array', () => {
    const session = makeSession({ resolved_tracks: [] });
    const model = buildSharedCanvasPresentationModel(session);
    expect(model.tracks).toHaveLength(0);
    expect(model.curveCatalog).toHaveLength(0);
  });

});


describe('extractBoundCurveUids', () => {

  it('returns managed_curve_uid for every BOUND slot', () => {
    const bound = makeBoundSlot({ managed_curve_uid: 'c1' });
    const track = makeTrack({ slots: [bound] });
    const session = makeSession({ resolved_tracks: [track] });
    const result = extractBoundCurveUids(session);
    expect(result).toEqual(['c1']);
  });

  it('skips non-BOUND slots', () => {
    const unavail = makeUnavailableSlot();
    const track = makeTrack({ slots: [unavail] });
    const session = makeSession({ resolved_tracks: [track] });
    expect(extractBoundCurveUids(session)).toHaveLength(0);
  });

  it('deduplicates curve UIDs appearing in multiple slots', () => {
    const s1 = makeBoundSlot({ slot_uid: 's1', managed_curve_uid: 'same-curve' });
    const s2 = makeBoundSlot({ slot_uid: 's2', managed_curve_uid: 'same-curve' });
    const track = makeTrack({ slots: [s1, s2] });
    const session = makeSession({ resolved_tracks: [track] });
    const result = extractBoundCurveUids(session);
    expect(result).toHaveLength(1);
    expect(result[0]).toBe('same-curve');
  });

  it('collects BOUND curve UIDs across multiple tracks', () => {
    const t1 = makeTrack({ track_uid: 't1', slots: [makeBoundSlot({ managed_curve_uid: 'c1' })] });
    const t2 = makeTrack({ track_uid: 't2', slots: [makeBoundSlot({ slot_uid: 's2', managed_curve_uid: 'c2' })] });
    const session = makeSession({ resolved_tracks: [t1, t2] });
    const result = extractBoundCurveUids(session);
    expect(result.sort()).toEqual(['c1', 'c2']);
  });

});
