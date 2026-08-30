import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { buildUniformCurveDisplayTrajectory } from '../selectedPointTracking/uniformCurveDisplayTrajectory';

type Point = { md: number; tvd: number };
const points: Point[] = [
  { md: 0, tvd: 0 },
  { md: 1, tvd: 0.8 },
  { md: 2, tvd: 1.4 },
];
const positions = [
  new THREE.Vector3(0, 0, 0),
  new THREE.Vector3(0.4, -0.8, 0),
  new THREE.Vector3(1.1, -1.4, 0),
];
const curve = new THREE.CatmullRomCurve3(positions, false, 'catmullrom', 0.02);
const interpolate = (a: Point, b: Point, ratio: number): Point => ({
  md: a.md + (b.md - a.md) * ratio,
  tvd: a.tvd + (b.tvd - a.tvd) * ratio,
});

describe('uniform curved display trajectory', () => {
  it('preserves every source station exactly', () => {
    const samples = buildUniformCurveDisplayTrajectory(points, positions, curve, interpolate, 0.25);
    const sourceSamples = samples.filter((sample) => sample.sourceStation);
    expect(sourceSamples).toHaveLength(3);
    expect(sourceSamples.map((sample) => sample.point.md)).toEqual([0, 1, 2]);
    expect(sourceSamples[1].position.equals(positions[1])).toBe(true);
  });

  it('inserts evenly distributed MD samples no farther apart than the cap', () => {
    const samples = buildUniformCurveDisplayTrajectory(points, positions, curve, interpolate, 0.25);
    for (let index = 1; index < samples.length; index += 1) {
      expect(samples[index].point.md - samples[index - 1].point.md).toBeLessThanOrEqual(0.2500001);
    }
  });

  it('places intermediate samples on the rendered Catmull-Rom curve', () => {
    const samples = buildUniformCurveDisplayTrajectory(points, positions, curve, interpolate, 0.25);
    const sample = samples.find((item) => item.sourceSegmentIndex === 0 && item.sourceRatio === 0.5);
    expect(sample).toBeDefined();
    expect(sample?.position.distanceTo(curve.getPoint(0.25))).toBeLessThan(1e-9);
  });
});
