import type {
  ManagedCurveUid,
} from '../identity/wdvIdentityV21';
import type {
  ManagedCurveSampleV21,
  ManagedCurveSamplesByUidV21,
} from '../prototype/managedCurveSamplesV21';
import type {
  CurveAssignmentV21,
  CurveTrackV21,
} from '../prototype/trackLayoutModelV21';

export interface CanonicalRenderPoint {
  depth: number;
  x: number;
  y: number;
}

export interface CanonicalCurveRenderSeries {
  managedCurveUid: ManagedCurveUid;
  assignment: CurveAssignmentV21;
  points: CanonicalRenderPoint[];
}

export function renderSeriesForTrack(
  track: CurveTrackV21,
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21,
  depthRange: { minimum: number; maximum: number },
  viewport: { width: number; height: number },
): CanonicalCurveRenderSeries[] {
  const depthSpan = depthRange.maximum - depthRange.minimum;
  if (!(depthSpan > 0) || viewport.width <= 0 || viewport.height <= 0) return [];

  return [...track.curves]
    .sort((left, right) => left.stackIndex - right.stackIndex)
    .filter((assignment) => assignment.visible)
    .map((assignment) => ({
      managedCurveUid: assignment.managedCurveUid,
      assignment,
      points: mapSamples(
        samplesByManagedCurveUid.get(assignment.managedCurveUid) ?? [],
        assignment,
        depthRange,
        viewport,
      ),
    }));
}

function mapSamples(
  samples: readonly ManagedCurveSampleV21[],
  assignment: CurveAssignmentV21,
  depthRange: { minimum: number; maximum: number },
  viewport: { width: number; height: number },
): CanonicalRenderPoint[] {
  // Null bounds (Tier-3 no-bounds fallback) cannot produce render points.
  if (assignment.scaleMin === null || assignment.scaleMax === null) return [];
  // Capture as const so TypeScript tracks the narrowed number type through the .map() closure.
  const scaleMin = assignment.scaleMin;
  const scaleSpan = assignment.scaleMax - scaleMin;
  const depthSpan = depthRange.maximum - depthRange.minimum;
  if (!(scaleSpan !== 0) || !(depthSpan > 0)) return [];

  return samples
    .filter((sample) => (
      sample.depth >= depthRange.minimum
      && sample.depth <= depthRange.maximum
      && Number.isFinite(sample.value)
    ))
    .map((sample) => {
      let normalized = (sample.value - scaleMin) / scaleSpan;
      if (assignment.scaleDirection === 'reverse') normalized = 1 - normalized;
      if (assignment.clipToTrack) normalized = Math.min(1, Math.max(0, normalized));
      normalized += assignment.horizontalOffsetPct / 100;
      return {
        depth: sample.depth,
        x: normalized * viewport.width,
        y:
          ((sample.depth - depthRange.minimum) / depthSpan)
          * viewport.height,
      };
    });
}
