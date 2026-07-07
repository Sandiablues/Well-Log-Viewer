import { describe, expect, it } from "vitest";
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import {
  markerScaleForZoom,
  markerSmoothingAlpha,
  surveyStationPointSizeForZoom,
  textSpriteScaleForZoom,
} from '../WellboreTrajectoryRenderer';

const here = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(here, '../Wellbore3DPage.tsx'), 'utf8');
const rendererSource = readFileSync(resolve(here, '../WellboreTrajectoryRenderer.tsx'), 'utf8');

describe('WBV marker presentation', () => {
  it('starts with survey stations disabled', () => {
    expect(pageSource).toMatch(/surveyStations:\s*false/);
    expect(rendererSource).toMatch(/showSurveyStations\s*=\s*false/);
  });

  it('uses small blue always-front zoom-aware survey station points', () => {
    expect(rendererSource).toContain('color: 0x2f9bff');
    expect(rendererSource).toContain('surveyStations.renderOrder = 120');
    expect(surveyStationPointSizeForZoom(1)).toBeCloseTo(4.2, 6);
    expect(surveyStationPointSizeForZoom(64)).toBeLessThan(2.5);
    expect(surveyStationPointSizeForZoom(64)).toBeGreaterThanOrEqual(2.0);
  });

  it('reduces marker scale as zoom increases', () => {
    expect(markerScaleForZoom(1)).toBeGreaterThan(markerScaleForZoom(16));
    expect(markerScaleForZoom(128)).toBeLessThanOrEqual(0.2);
    expect(rendererSource).toContain('marker.scale.setScalar(0.105 * markerScale)');
  });

  it('uses time-based visual smoothing without changing backend dispatch cadence', () => {
    const normal = markerSmoothingAlpha(16.67, 1);
    const highZoom = markerSmoothingAlpha(16.67, 64);
    expect(normal).toBeGreaterThan(0);
    expect(normal).toBeLessThan(1);
    expect(highZoom).toBeGreaterThan(0);
    expect(highZoom).toBeLessThan(normal);
    expect(rendererSource).toContain('const DRAG_BACKEND_INTERVAL_MS = 75');
    expect(rendererSource).toContain('basePosition.lerp(targetPosition, smoothingAlpha)');
  });

  it('draws thinner bullseye rings', () => {
    expect(rendererSource).toContain('context.lineWidth = 6');
    expect(rendererSource).toContain('context.lineWidth = 5');
    expect(rendererSource).not.toContain('context.lineWidth = 10');
  });
  it('scales all Three.js text sprites down with zoom and clamps the result', () => {
    expect(textSpriteScaleForZoom(1)).toBeCloseTo(1, 6);
    expect(textSpriteScaleForZoom(8)).toBeLessThan(textSpriteScaleForZoom(2));
    expect(textSpriteScaleForZoom(100)).toBeGreaterThanOrEqual(0.08);
    expect(textSpriteScaleForZoom(100)).toBeLessThanOrEqual(0.1);
    expect(rendererSource).toContain('zoomScaledTextSprites.push(label)');
    expect(rendererSource).toContain('zoomScaledTextSprites.push(baseLabel)');
    expect(rendererSource).toContain('sprite.scale.copy(baseScale).multiplyScalar(textScale)');
  });

});
