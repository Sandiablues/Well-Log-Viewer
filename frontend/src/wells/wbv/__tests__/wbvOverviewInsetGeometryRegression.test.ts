import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const readSource = (relativePath: string): string =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8');

const pageCss = readSource('../Wellbore3DPage.css');
const rendererSource = readSource('../WellboreTrajectoryRenderer.tsx');
const sharedCss = readSource('../../../styles/track-layout-prototype.css');

describe('WBV overview inset renderer geometry regression', () => {
  it('preserves the shared absolute full-frame renderer host', () => {
    expect(sharedCss).toMatch(
      /\.wlv-wbv-trajectory-renderer\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?inset:\s*0;/,
    );
    expect(pageCss).not.toMatch(
      /\.wlv-wbv-trajectory-renderer\s*\{[^}]*position:\s*relative;/,
    );
  });

  it('positions only the overview as an absolute child', () => {
    expect(pageCss).toMatch(
      /\.wlv-wbv-overview\s*\{[\s\S]*?position:\s*absolute;/,
    );
  });

  it('keeps inset work after the primary render and isolates update failure', () => {
    const renderIndex = rendererSource.indexOf('renderer.render(scene, camera)');
    const frameIndex = rendererSource.indexOf(
      'window.requestAnimationFrame(renderScene)',
      renderIndex,
    );
    const overviewIndex = rendererSource.indexOf('updateOverviewFocus()', frameIndex);

    expect(renderIndex).toBeGreaterThan(-1);
    expect(frameIndex).toBeGreaterThan(renderIndex);
    expect(overviewIndex).toBeGreaterThan(frameIndex);
    expect(rendererSource).toContain(
      "console.error('WBV overview disabled after isolated update failure'",
    );
  });
});
