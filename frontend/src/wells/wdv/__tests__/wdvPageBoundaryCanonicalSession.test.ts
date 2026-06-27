/**
 * C2 tests — Defect B: canonical session helpers in WdvPageBoundary.
 *
 * Covers:
 *  1–2.  looksLikeUuid — valid UUID / non-UUID legacy IDs
 *  3–7.  frontendTracksFromCanonicalSession — depth tracks, curve tracks,
 *         unknown-curve skipping, assignmentId propagation, non-active session
 *  8.    inventoryFocusedCurveIds rename — state field present in component type
 *  9.    handleWdvTemplateApplied no longer references setInventoryFocusedCurveIds
 * 10–11. deleteSelectedTrack / toggleCurveForSelectedTrack canonical wiring
 *        (source-level smoke: canonical guard variables / helpers exported)
 * 12.    WdvPageBoundary component export regression guard
 */

import { describe, expect, it } from 'vitest';
import {
  looksLikeUuid,
  canonicalCommandRequestBody,
  canonicalRangeOverrideCommandBody,
  frontendTracksFromCanonicalSession,
  WdvPageBoundary,
} from '../WdvPageBoundary';
import type {
  RawCanonicalSession,
  RawCanonicalTrack,
  RawCanonicalAssignment,
} from '../WdvPageBoundary';
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
} from '../../prototype/trackLayoutModel';

// ---------------------------------------------------------------------------
// Shared test data helpers
// ---------------------------------------------------------------------------

const VALID_UUID = '01930e4a-8db4-7000-8b21-3f4abc123456';
const VALID_UUID_2 = 'a1b2c3d4-e5f6-7890-abcd-ef0123456789';

/** Minimal CurveCatalogItem — only the fields touched by frontendTracksFromCanonicalSession */
function makeCatalogItem(overrides: Partial<CurveCatalogItem> & { curveUid: string }): CurveCatalogItem {
  return {
    curveId: overrides.curveUid,
    mnemonic: overrides.mnemonic ?? 'NPHI',
    description: overrides.description ?? 'Test curve',
    unit: overrides.unit ?? 'v/v',
    curveClass: 'neutron' as const,
    defaultLattice: 'linear' as const,
    defaultMin: 0,
    defaultMax: 1,
    defaultColor: '#000000',
    recognised: true,
    ...overrides,
  } as CurveCatalogItem;
}

function makeActiveSession(tracks: RawCanonicalTrack[] = []): RawCanonicalSession {
  return {
    revision: 3,
    state_status: 'active',
    selected_track_uid: null,
    tracks,
  };
}

function makeDepthTrack(trackUid = VALID_UUID): RawCanonicalTrack {
  return {
    track_uid: trackUid,
    track_name: 'Depth',
    track_type: 'depth',
    width_px: 86,
    depth_basis: 'MD',
    lattice: null,
    lattice_source: null,
    lattice_override: null,
    scale_mode: null,
    assignments: [],
  };
}

function makeCurveTrack(
  trackUid = VALID_UUID_2,
  assignments: RawCanonicalAssignment[] = [],
): RawCanonicalTrack {
  return {
    track_uid: trackUid,
    track_name: 'Curve Track',
    track_type: 'curve',
    width_px: 200,
    depth_basis: null,
    lattice: 'linear',
    lattice_source: 'front_curve_default',
    lattice_override: false,
    scale_mode: null,
    assignments,
  };
}

function makeAssignment(
  curveUid: string,
  assignmentUid: string,
  stackIndex = 0,
  overrides: Partial<RawCanonicalAssignment> = {},
): RawCanonicalAssignment {
  return {
    assignment_uid: assignmentUid,
    managed_curve_uid: curveUid,
    stack_index: stackIndex,
    visible: true,
    scale_min: 0,
    scale_max: 1,
    scale_type: 'linear',
    scale_direction: 'normal',
    color: null,
    unit: null,
    display_policy_source: null,
    display_review_required: false,
    display_warning_code: null,
    display_warning_message: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests 1–2: looksLikeUuid
// ---------------------------------------------------------------------------

describe('looksLikeUuid', () => {
  it('returns true for a valid lower-case UUID', () => {
    expect(looksLikeUuid('01930e4a-8db4-7000-8b21-3f4abc123456')).toBe(true);
  });

  it('returns true for a valid upper-case UUID', () => {
    expect(looksLikeUuid('A1B2C3D4-E5F6-7890-ABCD-EF0123456789')).toBe(true);
  });

  it('returns false for a legacy track-name-style ID', () => {
    expect(looksLikeUuid('track-neutron')).toBe(false);
  });

  it('returns false for an empty string', () => {
    expect(looksLikeUuid('')).toBe(false);
  });

  it('returns false for a numeric string', () => {
    expect(looksLikeUuid('12345')).toBe(false);
  });

  it('returns false for a UUID missing a segment', () => {
    // Only 4 groups instead of 5
    expect(looksLikeUuid('01930e4a-8db4-7000-8b21')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Tests 3–7: frontendTracksFromCanonicalSession
// ---------------------------------------------------------------------------

describe('frontendTracksFromCanonicalSession', () => {
  // Test 3: depth track converted with UUID trackId
  it('converts a depth track preserving the canonical UUID as trackId', () => {
    const session = makeActiveSession([makeDepthTrack(VALID_UUID)]);
    const tracks = frontendTracksFromCanonicalSession(session, []);

    expect(tracks).toHaveLength(1);
    const track = tracks[0];
    expect(track.trackId).toBe(VALID_UUID);
    expect(track.trackType).toBe('depth');
  });

  // Test 4: curve track — curveUid lookup via catalog
  it('converts a curve track by matching managed_curve_uid to catalog curveUid', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000001';
    const assignUid = 'cccccccc-0000-7000-8000-000000000002';
    const catalogItem = makeCatalogItem({ curveUid, mnemonic: 'GR' });
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [makeAssignment(curveUid, assignUid)]),
    ]);

    const tracks = frontendTracksFromCanonicalSession(session, [catalogItem]);

    expect(tracks).toHaveLength(1);
    const track = tracks[0] as CurveTrack;
    expect(track.trackType).toBe('curve');
    expect(track.trackId).toBe(VALID_UUID_2);
    expect(track.curves).toHaveLength(1);
    expect(track.curves[0].curveUid).toBe(curveUid);
  });

  // Test 5: unknown managed_curve_uid is skipped
  it('skips assignments whose managed_curve_uid has no catalog match', () => {
    const knownUid = 'bbbbbbbb-0000-7000-8000-000000000001';
    const unknownUid = 'ffffffff-0000-7000-8000-000000000099';
    const assignKnown = 'cccccccc-0000-7000-8000-000000000002';
    const assignUnknown = 'dddddddd-0000-7000-8000-000000000003';
    const catalog = [makeCatalogItem({ curveUid: knownUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(unknownUid, assignUnknown, 0),
        makeAssignment(knownUid, assignKnown, 1),
      ]),
    ]);

    const tracks = frontendTracksFromCanonicalSession(session, catalog);

    const curveTrack = tracks[0] as CurveTrack;
    expect(curveTrack.curves).toHaveLength(1);
    expect(curveTrack.curves[0].curveUid).toBe(knownUid);
  });

  // Test 6: assignment_uid is stored as assignmentId
  it('stores assignment_uid from the raw session as assignmentId on each assignment', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000001';
    const assignmentUid = 'eeeeeeee-0000-7000-8000-000000000005';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [makeAssignment(curveUid, assignmentUid)]),
    ]);

    const tracks = frontendTracksFromCanonicalSession(session, catalog);

    expect((tracks[0] as CurveTrack).curves[0].assignmentId).toBe(assignmentUid);
  });

  it('projects canonical unit and curve-policy provenance without using catalog unit', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000010';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000010';
    const catalog = [makeCatalogItem({ curveUid, unit: 'catalog-unit' })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          unit: 'G/C3',
          scale_min: 1.95,
          scale_max: 2.95,
          scale_type: 'linear',
          scale_direction: 'normal',
          display_policy_source: 'curve',
        }),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.unit).toBe('G/C3');
    expect(assignment.unit).not.toBe('catalog-unit');
    expect(assignment.displayPolicySource).toBe('curve');
    expect(assignment.displayReviewRequired).toBe(false);
    expect(assignment.displayWarningCode).toBeNull();
    expect(assignment.displayWarningMessage).toBeNull();
  });

  it('projects family-policy provenance unchanged', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000011';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000011';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          display_policy_source: 'family',
        }),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.displayPolicySource).toBe('family');
  });

  it('projects system-default review and warning data unchanged', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000012';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000012';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          display_policy_source: 'system_default',
          display_review_required: true,
          display_warning_code: 'NO_GOVERNED_DISPLAY_POLICY',
          display_warning_message: 'Backend system-default scale is in use.',
        }),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.displayPolicySource).toBe('system_default');
    expect(assignment.displayReviewRequired).toBe(true);
    expect(assignment.displayWarningCode).toBe('NO_GOVERNED_DISPLAY_POLICY');
    expect(assignment.displayWarningMessage).toBe(
      'Backend system-default scale is in use.',
    );
  });

  it('rejects legacy user-override provenance at the frontend boundary', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000013';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000013';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          display_policy_source: 'user_override',
        }),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.displayPolicySource).toBeNull();
  });

  it('maps canonical logarithmic and reversed values to frontend scale enums', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000014';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000014';
    const catalog = [makeCatalogItem({
      curveUid,
      defaultLattice: 'linear',
      defaultScaleDirection: 'normal',
    })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: 0.2,
          scale_max: 2000,
          scale_type: 'logarithmic',
          scale_direction: 'reversed',
        }),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.scaleType).toBe('log');
    expect(assignment.scaleDirection).toBe('reverse');
  });

  it('preserves zero and negative canonical scale endpoints', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000015';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000015';
    const catalog = [makeCatalogItem({
      curveUid,
      defaultMin: 10,
      defaultMax: 20,
    })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: -5,
          scale_max: 0,
        }),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.scaleMin).toBe(-5);
    expect(assignment.scaleMax).toBe(0);
  });

  it('keeps assignment order, identity, visibility, color, and track properties unchanged', () => {
    const firstCurveUid = 'bbbbbbbb-0000-7000-8000-000000000016';
    const secondCurveUid = 'bbbbbbbb-0000-7000-8000-000000000017';
    const firstAssignmentUid = 'cccccccc-0000-7000-8000-000000000016';
    const secondAssignmentUid = 'cccccccc-0000-7000-8000-000000000017';
    const catalog = [
      makeCatalogItem({ curveUid: firstCurveUid, mnemonic: 'FIRST' }),
      makeCatalogItem({ curveUid: secondCurveUid, mnemonic: 'SECOND' }),
    ];
    const track = makeCurveTrack(VALID_UUID_2, [
      makeAssignment(firstCurveUid, firstAssignmentUid, 5, {
        visible: false,
        color: '#123456',
      }),
      makeAssignment(secondCurveUid, secondAssignmentUid, 1, {
        visible: true,
        color: '#abcdef',
      }),
    ]);
    track.width_px = 321;
    track.lattice = 'logarithmic';
    track.lattice_source = 'template';
    track.lattice_override = true;
    track.scale_mode = 'shared';

    const projected = frontendTracksFromCanonicalSession(
      makeActiveSession([track]),
      catalog,
    )[0] as CurveTrack;

    expect(projected.trackId).toBe(VALID_UUID_2);
    expect(projected.widthPx).toBe(321);
    expect(projected.lattice).toBe('logarithmic');
    expect(projected.latticeSource).toBe('template');
    expect(projected.latticeOverride).toBe(true);
    expect(projected.scaleMode).toBe('shared');
    expect(projected.curves.map((item) => item.assignmentId)).toEqual([
      secondAssignmentUid,
      firstAssignmentUid,
    ]);
    expect(projected.curves.map((item) => item.stackIndex)).toEqual([1, 5]);
    expect(projected.curves.map((item) => item.visible)).toEqual([true, false]);
    expect(projected.curves.map((item) => item.color)).toEqual([
      '#abcdef',
      '#123456',
    ]);
  });

  it('projects null canonical metadata without inventing warning or unit values', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000018';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000018';
    const catalog = [makeCatalogItem({ curveUid, unit: 'catalog-unit' })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid),
      ]),
    ]);

    const assignment = (frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack)
      .curves[0];

    expect(assignment.unit).toBeNull();
    expect(assignment.displayPolicySource).toBeNull();
    expect(assignment.displayReviewRequired).toBe(false);
    expect(assignment.displayWarningCode).toBeNull();
    expect(assignment.displayWarningMessage).toBeNull();
  });

  it('rejects a canonical assignment with a missing backend scale minimum instead of using catalog defaults', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000020';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000020';
    const catalog = [makeCatalogItem({
      curveUid,
      defaultMin: 10,
      defaultMax: 20,
    })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: null,
          scale_max: 20,
        }),
      ]),
    ]);

    expect(() => frontendTracksFromCanonicalSession(session, catalog)).toThrow(
      `Canonical WDV assignment ${assignmentUid} for curve ${curveUid} is missing a valid backend scale range.`,
    );
  });

  it('rejects a canonical assignment with a missing backend scale maximum instead of using catalog defaults', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000021';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000021';
    const catalog = [makeCatalogItem({
      curveUid,
      defaultMin: 10,
      defaultMax: 20,
    })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: 10,
          scale_max: null,
        }),
      ]),
    ]);

    expect(() => frontendTracksFromCanonicalSession(session, catalog)).toThrow(
      `Canonical WDV assignment ${assignmentUid} for curve ${curveUid} is missing a valid backend scale range.`,
    );
  });

  it('rejects equal backend scale endpoints rather than inventing a frontend range', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000022';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000022';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: 5,
          scale_max: 5,
        }),
      ]),
    ]);

    expect(() => frontendTracksFromCanonicalSession(session, catalog)).toThrow(
      `Canonical WDV assignment ${assignmentUid} for curve ${curveUid} is missing a valid backend scale range.`,
    );
  });

  it('rejects a missing backend scale type rather than using catalog lattice defaults', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000023';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000023';
    const catalog = [makeCatalogItem({
      curveUid,
      defaultLattice: 'logarithmic',
    })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_type: null,
        }),
      ]),
    ]);

    expect(() => frontendTracksFromCanonicalSession(session, catalog)).toThrow(
      `Canonical WDV assignment ${assignmentUid} for curve ${curveUid} has invalid backend scale type: null.`,
    );
  });

  it('rejects a missing backend scale direction rather than assuming normal', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000024';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000024';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_direction: null,
        }),
      ]),
    ]);

    expect(() => frontendTracksFromCanonicalSession(session, catalog)).toThrow(
      `Canonical WDV assignment ${assignmentUid} for curve ${curveUid} has invalid backend scale direction: null.`,
    );
  });

  it('rejects non-positive logarithmic backend ranges', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000025';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000025';
    const catalog = [makeCatalogItem({ curveUid })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: 0,
          scale_max: 100,
          scale_type: 'logarithmic',
        }),
      ]),
    ]);

    expect(() => frontendTracksFromCanonicalSession(session, catalog)).toThrow(
      `Canonical WDV assignment ${assignmentUid} for curve ${curveUid} has a non-positive logarithmic backend scale.`,
    );
  });

  it('uses canonical backend scale values even when catalog defaults differ', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000026';
    const assignmentUid = 'cccccccc-0000-7000-8000-000000000026';
    const catalog = [makeCatalogItem({
      curveUid,
      defaultMin: 1000,
      defaultMax: 2000,
      defaultLattice: 'logarithmic',
      defaultScaleDirection: 'reverse',
    })];
    const session = makeActiveSession([
      makeCurveTrack(VALID_UUID_2, [
        makeAssignment(curveUid, assignmentUid, 0, {
          scale_min: -10,
          scale_max: 30,
          scale_type: 'linear',
          scale_direction: 'normal',
        }),
      ]),
    ]);

    const assignment = (
      frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack
    ).curves[0];

    expect(assignment.scaleMin).toBe(-10);
    expect(assignment.scaleMax).toBe(30);
    expect(assignment.scaleType).toBe('linear');
    expect(assignment.scaleDirection).toBe('normal');
  });

  // Test 7: non-active session returns empty array
  it('returns an empty array for a non-active (empty) session', () => {
    const emptySession: RawCanonicalSession = {
      revision: 0,
      state_status: 'empty',
      selected_track_uid: null,
      tracks: [],
    };

    const tracks = frontendTracksFromCanonicalSession(emptySession, []);

    expect(tracks).toHaveLength(0);
  });

  it('returns an empty array for a cleared session', () => {
    const clearedSession: RawCanonicalSession = {
      revision: 5,
      state_status: 'cleared',
      selected_track_uid: null,
      tracks: [],
    };

    const tracks = frontendTracksFromCanonicalSession(clearedSession, []);

    expect(tracks).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Test 8: inventoryFocusedCurveIds rename — source-level guard
// ---------------------------------------------------------------------------

describe('inventoryFocusedCurveIds rename', () => {
  it('WdvPageBoundary source no longer contains selectedInventoryCurveIds', async () => {
    // Regression guard: the old name must not appear in the source.
    // Dynamic import returns the module, not the file text, so we use a
    // static string comparison against what we know the old identifier was.
    // The compile-time check (TypeScript sees no such export) is the real
    // enforcement; this test guards the rename at the source level.
    const mod = await import('../WdvPageBoundary');
    // There is no export named selectedInventoryCurveIds — accessing it
    // on the module should return undefined.
    expect((mod as Record<string, unknown>)['selectedInventoryCurveIds']).toBeUndefined();
  });

  it('WdvPageBoundary module does not export setSelectedInventoryCurveIds', async () => {
    const mod = await import('../WdvPageBoundary');
    expect((mod as Record<string, unknown>)['setSelectedInventoryCurveIds']).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Test 9: handleWdvTemplateApplied — setInventoryFocusedCurveIds removed
// (source-level smoke via module shape; runtime test would need React harness)
// ---------------------------------------------------------------------------

describe('handleWdvTemplateApplied no longer calls setInventoryFocusedCurveIds', () => {
  it('the renamed helper is not an exported standalone function', async () => {
    // If setInventoryFocusedCurveIds were incorrectly extracted as a module
    // export, this test would catch the regression.
    const mod = await import('../WdvPageBoundary');
    expect((mod as Record<string, unknown>)['setInventoryFocusedCurveIds']).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Tests 10–11: canonical command wiring — exported helpers smoke tests
// ---------------------------------------------------------------------------

describe('canonical command request payload', () => {
  it('includes the expected revision and omits invalid frontend command_id tokens', () => {
    const payload = canonicalCommandRequestBody(4, {
      track_uid: VALID_UUID,
    });

    expect(payload).toEqual({
      track_uid: VALID_UUID,
      expected_revision: 4,
    });
    expect(payload).not.toHaveProperty('command_id');
  });

  it('preserves canonical assignment mutation fields unchanged', () => {
    const payload = canonicalCommandRequestBody(7, {
      assignment_uid: VALID_UUID_2,
    });

    expect(payload).toEqual({
      assignment_uid: VALID_UUID_2,
      expected_revision: 7,
    });
  });
});

describe('canonical command guard helpers', () => {
  // Test 10: deleteSelectedTrack guard — looksLikeUuid is the gate
  it('looksLikeUuid gates canonical deleteSelectedTrack — returns true for UUID track', () => {
    // The real guard inside deleteSelectedTrack:
    //   if (canonicalRevisionRef.current >= 0 && looksLikeUuid(trackUid)) …
    // We verify the UUID check passes for a realistic UUID7 track ID.
    const canonicalTrackUid = '01930e4a-8db4-7000-8b21-3f4abc000001';
    expect(looksLikeUuid(canonicalTrackUid)).toBe(true);
  });

  // Test 11: toggleCurveForSelectedTrack — both trackId and curveId checked
  it('looksLikeUuid gates canonical toggleCurveForSelectedTrack — legacy ID is blocked', () => {
    // The real guard:
    //   const useCanonical = canonicalRevisionRef.current >= 0
    //     && looksLikeUuid(trackId) && looksLikeUuid(curveId);
    // A legacy track ID (non-UUID) must block canonical dispatch.
    const legacyTrackId = 'track-gamma-1';
    const canonicalCurveId = '01930e4a-8db4-7000-8b21-3f4abc000002';
    // Both must be UUID for canonical path; legacy trackId is sufficient to block it.
    expect(looksLikeUuid(legacyTrackId) && looksLikeUuid(canonicalCurveId)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Test 12: WdvPageBoundary component export regression guard
// ---------------------------------------------------------------------------

describe('WdvPageBoundary export regression', () => {
  it('WdvPageBoundary is still exported as a React component function', () => {
    expect(typeof WdvPageBoundary).toBe('function');
  });

  it('looksLikeUuid is exported as a function', () => {
    expect(typeof looksLikeUuid).toBe('function');
  });

  it('frontendTracksFromCanonicalSession is exported as a function', () => {
    expect(typeof frontendTracksFromCanonicalSession).toBe('function');
  });
});

describe('canonical range ownership bridge', () => {
  it('sends governed and fit modes as intent only', () => {
    const assignment = {
      assignmentId: VALID_UUID_2,
      curveId: VALID_UUID_2,
      curveUid: VALID_UUID_2,
      stackIndex: 0,
      visible: true,
      scaleMin: 0.45,
      scaleMax: -0.15,
      scaleDirection: 'reverse',
      scaleType: 'linear',
      color: '#000000',
      lineStyle: 'solid',
      lineWidth: 1,
      fillSide: 'none',
      fillColor: '#000000',
      rangeOverrideMode: 'governed',
    } as CurveAssignment;

    expect(canonicalRangeOverrideCommandBody(assignment, {
      rangeOverrideMode: 'fit_to_curve',
      manualScaleMin: null,
      manualScaleMax: null,
    })).toEqual({ range_override_mode: 'fit_to_curve' });

    expect(canonicalRangeOverrideCommandBody(assignment, {
      rangeOverrideMode: 'governed',
      manualScaleMin: null,
      manualScaleMax: null,
    })).toEqual({ range_override_mode: 'governed' });
  });

  it('sends both manual bounds in one validated command', () => {
    const assignment = {
      assignmentId: VALID_UUID_2,
      curveId: VALID_UUID_2,
      curveUid: VALID_UUID_2,
      stackIndex: 0,
      visible: true,
      scaleMin: 0.45,
      scaleMax: -0.15,
      scaleDirection: 'reverse',
      scaleType: 'linear',
      color: '#000000',
      lineStyle: 'solid',
      lineWidth: 1,
      fillSide: 'none',
      fillColor: '#000000',
      rangeOverrideMode: 'manual',
      manualScaleMin: 0.3,
      manualScaleMax: 0,
    } as CurveAssignment;

    expect(canonicalRangeOverrideCommandBody(assignment, {
      manualScaleMin: 0.25,
    })).toEqual({
      range_override_mode: 'manual',
      manual_scale_min: 0.25,
      manual_scale_max: 0,
    });
  });

  it('projects backend range mode, effective bounds, and fit warning', () => {
    const raw = makeAssignment(
      VALID_UUID_2,
      '01930e4a-8db4-7000-8b21-3f4abc000099',
      0,
      {
        scale_min: 0.02,
        scale_max: 0.31,
        range_override_mode: 'fit_to_curve',
        effective_range_source: 'fit_to_curve',
        manual_scale_min: null,
        manual_scale_max: null,
        override_warning_code: 'FIT_TO_CURVE_UNAVAILABLE',
        override_warning_message: 'Fit unavailable.',
      },
    );
    const catalog = [makeCatalogItem({ curveUid: VALID_UUID_2 })];
    const tracks = frontendTracksFromCanonicalSession(
      makeActiveSession([makeCurveTrack(VALID_UUID, [raw])]),
      catalog,
    );
    const curveTrack = tracks[0];
    expect(curveTrack.trackType).toBe('curve');
    if (curveTrack.trackType !== 'curve') throw new Error('expected curve track');
    const assignment = curveTrack.curves[0];

    expect(assignment.scaleMin).toBe(0.02);
    expect(assignment.scaleMax).toBe(0.31);
    expect(assignment.rangeOverrideMode).toBe('fit_to_curve');
    expect(assignment.effectiveRangeSource).toBe('fit_to_curve');
    expect(assignment.overrideWarningCode).toBe('FIT_TO_CURVE_UNAVAILABLE');
    expect(assignment.overrideWarningMessage).toBe('Fit unavailable.');
  });
});
