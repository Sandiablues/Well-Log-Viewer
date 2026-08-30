import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const sourcePath = path.resolve(process.cwd(), 'src/wells/wbv/WellboreTrajectoryRenderer.tsx');
const source = fs.readFileSync(sourcePath, 'utf8');

describe('WBV render-loop performance contract', () => {
  it('keeps curve interpolation and DOM measurement out of requestAnimationFrame', () => {
    const start = source.indexOf('const renderScene');
    const end = source.indexOf('resizeObserver =', start);
    const renderLoop = source.slice(start, end);
    expect(renderLoop).not.toContain('interpolateCurveValueAtMd');
    expect(renderLoop).not.toContain('getBoundingClientRect');
    expect(renderLoop).not.toContain('curveOverlays.map');
    expect(renderLoop).not.toContain('new THREE.Vector3()');
  });

  it('computes readout content only when authoritative interaction state is synchronized', () => {
    expect(source).toContain('const liveReadoutTextFor');
    expect(source).toContain('cachedLiveReadoutText = liveReadoutTextFor(point)');
    expect(source).toContain('translate3d(');
  });

  it('updates zoom-scaled objects only when zoom changes', () => {
    expect(source).toContain('if (camera.zoom !== lastAppliedZoom)');
  });
});
