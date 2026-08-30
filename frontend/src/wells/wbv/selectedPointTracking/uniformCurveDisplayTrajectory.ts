import * as THREE from 'three';

export type UniformCurveDisplaySample<TPoint> = Readonly<{
  point: TPoint;
  position: THREE.Vector3;
  sourceSegmentIndex: number;
  sourceRatio: number;
  sourceStation: boolean;
}>;

/**
 * Preserves every source station exactly and inserts evenly distributed MD
 * samples between adjacent stations. Intermediate scene positions are evaluated
 * on the same Catmull-Rom curve used to render the wellbore.
 */
export function buildUniformCurveDisplayTrajectory<TPoint extends { md?: number | null }>(
  sourcePoints: readonly TPoint[],
  sourcePositions: readonly THREE.Vector3[],
  curve: THREE.CatmullRomCurve3,
  interpolatePoint: (first: TPoint, second: TPoint, ratio: number) => TPoint,
  maximumMdSpacing = 0.25,
): readonly UniformCurveDisplaySample<TPoint>[] {
  if (sourcePoints.length !== sourcePositions.length || sourcePoints.length < 2) return [];
  const safeSpacing = Number.isFinite(maximumMdSpacing) && maximumMdSpacing > 0
    ? maximumMdSpacing
    : 0.25;
  const lastSourceIndex = sourcePoints.length - 1;
  const samples: UniformCurveDisplaySample<TPoint>[] = [];

  for (let segmentIndex = 0; segmentIndex < lastSourceIndex; segmentIndex += 1) {
    const first = sourcePoints[segmentIndex];
    const second = sourcePoints[segmentIndex + 1];
    const firstMd = first.md;
    const secondMd = second.md;
    const mdSpan = typeof firstMd === 'number' && Number.isFinite(firstMd)
      && typeof secondMd === 'number' && Number.isFinite(secondMd)
      ? Math.abs(secondMd - firstMd)
      : 0;
    const subdivisions = Math.max(1, Math.ceil(mdSpan / safeSpacing));

    for (let step = 0; step < subdivisions; step += 1) {
      const ratio = step / subdivisions;
      const curveParameter = (segmentIndex + ratio) / lastSourceIndex;
      samples.push({
        point: ratio === 0 ? first : interpolatePoint(first, second, ratio),
        position: ratio === 0
          ? sourcePositions[segmentIndex].clone()
          : curve.getPoint(curveParameter),
        sourceSegmentIndex: segmentIndex,
        sourceRatio: ratio,
        sourceStation: ratio === 0,
      });
    }
  }

  samples.push({
    point: sourcePoints[lastSourceIndex],
    position: sourcePositions[lastSourceIndex].clone(),
    sourceSegmentIndex: lastSourceIndex - 1,
    sourceRatio: 1,
    sourceStation: true,
  });
  return samples;
}
